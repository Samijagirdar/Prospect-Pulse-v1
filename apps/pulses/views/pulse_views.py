import json
import logging

logger = logging.getLogger('django.request')
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from django.db.models import Q

from common.auth import get_user_org, ensure_authenticated_dev
from common.utils import is_json_request
from ..models import Pulse, CompanyProfile, Persona, TargetCompetitor, Keyword, BuyingSignal
from ..forms import ProspectPulseForm
from ..services import pulse_service

def get_pulse_by_pk_or_uid(pk_or_uid, org_id=None):
    """
    Look up a Pulse campaign by its database ID or its secure unique uid string.
    """
    query = Q(uid=pk_or_uid)
    if str(pk_or_uid).isdigit():
        query |= Q(id=int(pk_or_uid))
        
    try:
        if org_id:
            return Pulse.objects.get(query, organisation_id=org_id)
        else:
            return Pulse.objects.get(query)
    except Pulse.DoesNotExist:
        return None


def pulse_list(request):
    if is_json_request(request):
        from .. import api_views
        return api_views.PulseListCreateAPIView.as_view()(request)
    else:
        ensure_authenticated_dev(request)
        org = get_user_org(request)
        pulses = []
        if org:
            pulses = Pulse.objects.filter(organisation_id=org.id).order_by('-created_at')
        return render(request, 'pulses/pulse_list.html', {'pulses': pulses, 'debug': settings.DEBUG})


@csrf_exempt
def pulse_create(request):
    if is_json_request(request):
        from .. import api_views
        return api_views.PulseListCreateAPIView.as_view()(request)
    else:
        ensure_authenticated_dev(request)
        org = get_user_org(request)
        if request.method == 'POST':
            form = ProspectPulseForm(request.POST, request.FILES, organisation=org)
            if form.is_valid():
                data = form.cleaned_data
                pdf_path = ""

                # Handle PDF file saving
                if request.FILES.get('pdf_file'):
                    from django.core.files.storage import default_storage
                    file = request.FILES['pdf_file']
                    pdf_path = default_storage.save(f"prospect_pulse/pdfs/{file.name}", file)

                from django.db import transaction
                try:
                    with transaction.atomic():
                        pulse_id = pulse_service.create_pulse_config(
                            org_id=org.id,
                            name=data['name'],
                            frequency=data['frequency'],
                            custom_days=data['custom_days'],
                            start_date=data['start_date'],
                            end_date=data['end_date'],
                            input_type=data['input_type'],
                            pdf_file=pdf_path,
                            url=data['url'],
                            text_content=data['text_content'],
                            from_document_id=int(data['from_document']) if data['from_document'] else None,
                            competitors=data['competitors']
                        )
                    pulse = Pulse.objects.get(id=pulse_id)
                    messages.success(request, f"Pulse '{data['name']}' created successfully.")
                    return redirect('prospect_pulse:prospect_pulse_detail', pk=pulse.uid)
                except Exception as e:
                    logger.error(f"Error creating pulse: {e}", exc_info=True)
                    error_msg = str(e)
                    if "Unable to parse valid JSON from LLM" in error_msg:
                        messages.error(request, "Failed to run GTM enrichment: AI returned an invalid response format. Please try again.")
                    elif any(keyword in error_msg for keyword in ["RESOURCE_EXHAUSTED", "quota", "spending cap", "429"]):
                        messages.error(request, "Failed to run GTM enrichment: Gemini API quota exceeded. Please verify your billing/credits.")
                    else:
                        messages.error(request, f"Error creating pulse: {error_msg}")
        else:
            form = ProspectPulseForm(organisation=org)
            
        context = {
            'form': form,
            'title': 'Create Prospect Pulse',
        }
        return render(request, 'pulses/pulse_form.html', context)


@csrf_exempt
def pulse_edit(request, pk):
    if is_json_request(request):
        from .. import api_views
        return api_views.PulseDetailAPIView.as_view()(request, pk=pk)
    else:
        ensure_authenticated_dev(request)
        org = get_user_org(request)
        pulse = get_pulse_by_pk_or_uid(pk, org.id)
        if not pulse:
            return HttpResponse("Pulse not found", status=404)
        next_page = request.GET.get('next', 'detail')

        if request.method == 'POST':
            form = ProspectPulseForm(request.POST, request.FILES, instance=pulse, organisation=org)
            if form.is_valid():
                data = form.cleaned_data
                pdf_path = pulse.pdf_file
                
                # Handle PDF upload changes
                if request.FILES.get('pdf_file'):
                    from django.core.files.storage import default_storage
                    file = request.FILES['pdf_file']
                    pdf_path = default_storage.save(f"prospect_pulse/pdfs/{file.name}", file)
                    
                try:
                    pulse_service.update_pulse_config(
                        pulse_id=pulse.id,
                        name=data['name'],
                        frequency=data['frequency'],
                        custom_days=data['custom_days'],
                        start_date=data['start_date'],
                        end_date=data['end_date'],
                        input_type=data['input_type'],
                        pdf_file=pdf_path,
                        url=data['url'],
                        text_content=data['text_content'],
                        from_document_id=int(data['from_document']) if data['from_document'] else None,
                        competitors=data['competitors']
                    )
                    
                    messages.success(request, f"Pulse '{data['name']}' updated successfully.")
                    if next_page == 'list':
                        return redirect('prospect_pulse:prospect_pulse_list')
                    return redirect('prospect_pulse:prospect_pulse_detail', pk=pk)
                except Exception as e:
                    logger.error(f"Error updating pulse: {e}", exc_info=True)
                    error_msg = str(e)
                    if "Unable to parse valid JSON from LLM" in error_msg:
                        messages.error(request, "Failed to run GTM enrichment: AI returned an invalid response format. Please try again.")
                    elif any(keyword in error_msg for keyword in ["RESOURCE_EXHAUSTED", "quota", "spending cap", "429"]):
                        messages.error(request, "Failed to run GTM enrichment: Gemini API quota exceeded. Please verify your billing/credits.")
                    else:
                        messages.error(request, f"Error updating pulse: {error_msg}")
        else:
            initial_data = {
                'competitors': ", ".join(pulse.competitors_list),
            }
            form = ProspectPulseForm(instance=pulse, initial=initial_data, organisation=org)
            
        context = {
            'form': form,
            'pulse_id': pk,
            'pulse': pulse,
            'next_page': next_page,
            'title': f'Edit Pulse: {pulse.name}',
        }
        return render(request, 'pulses/pulse_form.html', context)


def pulse_detail(request, pk):
    if is_json_request(request):
        from .. import api_views
        return api_views.PulseDetailAPIView.as_view()(request, pk=pk)
    else:
        ensure_authenticated_dev(request)
        org = get_user_org(request)
        pulse = get_pulse_by_pk_or_uid(pk, org.id)
        if not pulse:
            return HttpResponse("Pulse not found", status=404)
            
        articles = pulse.scraped_articles.all().order_by('-scraped_at')
        intent_articles = []
        deduplicated_sources = []
        noise_articles = []
        
        for art in articles:
            if art.is_duplicate:
                deduplicated_sources.append(art)
            elif art.is_relevant:
                intent_articles.append(art)
            else:
                noise_articles.append(art)
                
        # Check if there is an active running discovery run
        latest_run = pulse.discovery_runs.order_by('-started_at').first()
        active_run_id = None
        if latest_run and latest_run.status not in ['completed', 'failed']:
            active_run_id = latest_run.id
            
        context = {
            'pulse': pulse,
            'page_title': pulse.name,
            'debug': settings.DEBUG,
            'intent_articles': intent_articles,
            'deduplicated_sources': deduplicated_sources,
            'noise_articles': noise_articles,
            'intent_leads': pulse.extracted_leads.all().order_by('-extracted_at'),
            'intent_companies': pulse.extracted_companies.all().order_by('-extracted_at'),
            'intent_competitors': pulse.extracted_competitors.all().order_by('-extracted_at'),
            'active_run_id': active_run_id,
        }
        return render(request, 'pulses/pulse_detail.html', context)


@csrf_exempt
def pulse_delete(request, pk):
    if request.method not in ['POST', 'DELETE']:
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST', 'DELETE'])
        
    org = get_user_org(request)
    pulse = get_pulse_by_pk_or_uid(pk, org.id)
    if pulse:
        name = pulse.name
        pulse.delete()
        if request.method == 'DELETE' or is_json_request(request):
            from django.http import JsonResponse
            return JsonResponse({'success': True, 'message': f"Pulse '{name}' has been deleted."})
        messages.success(request, f"Pulse '{name}' has been deleted.")
    else:
        if request.method == 'DELETE' or is_json_request(request):
            from django.http import JsonResponse
            return JsonResponse({'success': False, 'error': 'Pulse not found'}, status=404)
            
    return redirect('prospect_pulse:prospect_pulse_list')


@csrf_exempt
@require_POST
def pulse_toggle(request, pk):
    if is_json_request(request):
        from .. import api_views
        return api_views.PulseToggleAPIView.as_view()(request, pk=pk)
    else:
        org = get_user_org(request)
        pulse = get_pulse_by_pk_or_uid(pk, org.id)
        if pulse:
            pulse.is_active = not pulse.is_active
            pulse.save()
            status_str = "activated" if pulse.is_active else "paused"
            messages.success(request, f"Pulse '{pulse.name}' has been {status_str}.")
            return redirect('prospect_pulse:prospect_pulse_detail', pk=pk)
        return redirect('prospect_pulse:prospect_pulse_list')


def pulse_discover(request, pk):
    ensure_authenticated_dev(request)
    org = get_user_org(request)
    pulse = get_pulse_by_pk_or_uid(pk, org.id)
    if not pulse:
        return HttpResponse("Pulse not found", status=404)
        
    from apps.discovery.tasks import run_pulse_discovery_task
    from apps.discovery.models import DiscoveryRun
    from django.http import JsonResponse
    
    # Create the run record in the main request thread
    run = DiscoveryRun.objects.create(
        pulse=pulse,
        status='starting',
        started_at=timezone.now()
    )
    
    # Trigger asynchronously via Celery
    run_pulse_discovery_task.delay(pulse.id, run.id)
    
    return JsonResponse({
        'success': True,
        'run_id': run.id,
        'message': 'Discovery campaign started in Celery background worker.'
    })


@csrf_exempt
@require_POST
def pulse_manage_item(request, pk):
    """Add or remove competitors, target focus chips, or personas for a pulse."""
    try:
        pulse = get_pulse_by_pk_or_uid(pk)
        if not pulse:
            return JsonResponse({'success': False, 'error': 'Pulse not found'}, status=404)

        data = json.loads(request.body.decode('utf-8'))
        item_type = data.get('item_type')
        action = data.get('action')
        value = (data.get('value') or '').strip()
        
        if not value:
            return JsonResponse({'success': False, 'error': 'Value cannot be empty'}, status=400)
            
        if item_type == 'competitor':
            if action == 'add':
                TargetCompetitor.objects.get_or_create(pulse=pulse, competitor_name=value)
            elif action == 'remove':
                TargetCompetitor.objects.filter(pulse=pulse, competitor_name=value).delete()
        elif item_type == 'persona':
            if action == 'add':
                Persona.objects.create(pulse=pulse, role=value, type="Target Role")
            elif action == 'remove':
                Persona.objects.filter(pulse=pulse, role=value).delete()
        elif item_type == 'focus':
            profile, _ = CompanyProfile.objects.get_or_create(pulse=pulse)
            current_focus = profile.target_account_focus or ""
            items = [x.strip() for x in current_focus.split(',') if x.strip()]
            if action == 'add':
                if value not in items:
                    items.append(value)
            elif action == 'remove':
                items = [x for x in items if x.lower() != value.lower()]
            profile.target_account_focus = ", ".join(items)
            profile.save()
        else:
            return JsonResponse({'success': False, 'error': 'Invalid item type'}, status=400)
            
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
