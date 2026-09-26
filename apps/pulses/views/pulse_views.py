import json
import logging
import re

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
                            org_id=org.id if org else None,
                            name=data['name'],
                            frequency=data['frequency'],
                            start_date=data['start_date'],
                            end_date=data.get('end_date'),
                            input_type=data['input_type'],
                            pdf_file=pdf_path,
                            url=data.get('url'),
                            text_content=data.get('text_content'),
                            from_document_id=int(data['from_document']) if data.get('from_document') else None,
                            competitors=data.get('competitors', ''),
                            historical_lookback=data.get('historical_lookback', '60d'),
                            target_geography=data.get('target_geography')
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
                    elif any(keyword in error_msg for keyword in ["PERMISSION_DENIED", "CONSUMER_SUSPENDED", "403", "UNAUTHENTICATED", "401", "api_key"]):
                        messages.error(request, "API Error please contact your administrator")
                    else:
                        import re
                        clean_msg = re.sub(r'api_key[=:][A-Za-z0-9_\-]+', 'api_key=***HIDDEN***', error_msg)
                        messages.error(request, f"Error creating pulse: {clean_msg}")
        else:
            form = ProspectPulseForm(organisation=org)
            
        context = {
            'form': form,
            'title': 'Create Prospect Pulse',
        }
        return render(request, 'pulses/pulse_form.html', context)


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
                    # In edit mode, ONLY name, end_date, competitors, and target_geography can be modified.
                    # All other fields strictly retain existing pulse settings.
                    pulse_service.update_pulse_config(
                        pulse_id=pulse.id,
                        name=data['name'],
                        frequency=pulse.frequency,
                        start_date=pulse.start_date,
                        end_date=data.get('end_date'),
                        input_type=pulse.input_type,
                        pdf_file=pulse.pdf_file,
                        url=pulse.url,
                        text_content=pulse.text_content,
                        from_document_id=pulse.from_document_id,
                        competitors=data.get('competitors', ''),
                        historical_lookback=pulse.historical_lookback,
                        target_geography=data.get('target_geography')
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
                    elif any(keyword in error_msg for keyword in ["PERMISSION_DENIED", "CONSUMER_SUSPENDED", "403", "UNAUTHENTICATED", "401", "api_key"]):
                        messages.error(request, "API Error please contact your administrator")
                    else:
                        import re
                        clean_msg = re.sub(r'api_key[=:][A-Za-z0-9_\-]+', 'api_key=***HIDDEN***', error_msg)
                        messages.error(request, f"Error updating pulse: {clean_msg}")
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
        if latest_run and latest_run.status not in ['completed', 'failed', 'stopped']:
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
    
    # Check if pulse end date has passed
    if pulse.is_expired:
        end_date_str = pulse.end_date.strftime('%d/%m/%Y') if pulse.end_date else ''
        edit_url = f"/pulses/{pulse.uid}/edit/"
        return JsonResponse({
            'success': False,
            'is_expired': True,
            'end_date': end_date_str,
            'edit_url': edit_url,
            'error': f"The end date for this pulse ({end_date_str}) has passed. Please edit your pulse and extend the end date to run discovery.",
            'message': f"The end date for this pulse ({end_date_str}) has passed. Please edit your pulse and extend the end date to run discovery."
        }, status=400)

    # Check if a discovery run is already actively running for this pulse
    active_run = pulse.discovery_runs.exclude(status__in=['completed', 'failed', 'stopped']).order_by('-started_at').first()

    if active_run:
        return JsonResponse({
            'success': False,
            'run_id': active_run.id,
            'message': 'A discovery scan is already actively executing for this campaign. Please wait for it to complete.'
        }, status=409)
    
    # Check for optional lookback override in request body or query params
    lookback_days = None
    try:
        if request.body:
            import json
            b_data = json.loads(request.body.decode('utf-8'))
            if b_data.get('lookback_days'):
                lookback_days = int(b_data.get('lookback_days'))
            elif b_data.get('force_lookback'):
                lookback_days = int(b_data.get('force_lookback'))
    except Exception:
        pass
    if not lookback_days and request.GET.get('lookback_days'):
        try:
            lookback_days = int(request.GET.get('lookback_days'))
        except Exception:
            pass

    # Create the run record in the main request thread
    run = DiscoveryRun.objects.create(
        pulse=pulse,
        status='starting',
        started_at=timezone.now()
    )
    
    # Trigger asynchronously via Celery (with optional lookback override)
    run_pulse_discovery_task.delay(pulse.id, run.id, timeframe_days_override=lookback_days)
    
    return JsonResponse({
        'success': True,
        'run_id': run.id,
        'message': 'Discovery campaign started in Celery background worker.'
    })


@require_POST
def pulse_manage_item(request, pk):
    """Add or remove competitors, target focus chips, or personas for a pulse."""
    try:
        ensure_authenticated_dev(request)
        org = get_user_org(request)
        pulse = get_pulse_by_pk_or_uid(pk, org.id)
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
                if not TargetCompetitor.objects.filter(pulse=pulse, competitor_name__iexact=value).exists():
                    TargetCompetitor.objects.create(pulse=pulse, competitor_name=value)
            elif action == 'remove':
                TargetCompetitor.objects.filter(pulse=pulse, competitor_name__iexact=value).delete()
        elif item_type == 'persona':
            if action == 'add':
                if pulse.personas_rel.count() >= 8:
                    return JsonResponse({'success': False, 'error': 'You cannot add more than 8 personas.'}, status=400)
                Persona.objects.create(pulse=pulse, role=value, type="Target Role")
            elif action == 'remove':
                Persona.objects.filter(pulse=pulse, role=value).delete()
        elif item_type == 'focus':
            profile, _ = CompanyProfile.objects.get_or_create(pulse=pulse)
            current_focus = profile.target_account_focus or ""
            items = [x.strip() for x in current_focus.split(',') if x.strip()]
            if action == 'add':
                if len(items) >= 8:
                    return JsonResponse({'success': False, 'error': 'You cannot add more than 8 target focus areas.'}, status=400)
                if value not in items:
                    items.append(value)
            elif action == 'remove':
                items = [x for x in items if x.lower() != value.lower()]
            profile.target_account_focus = ", ".join(items)
            profile.save()
        elif item_type == 'geography':
            current_geos = [x.strip() for x in (pulse.target_geography or '').split(',') if x.strip()]
            if action == 'add':
                if value not in current_geos:
                    current_geos.append(value)
            elif action == 'remove':
                current_geos = [x for x in current_geos if x.lower() != value.lower()]
            pulse.target_geography = ", ".join(current_geos) if current_geos else None
            pulse.save(update_fields=['target_geography', 'updated_at'])
        elif item_type == 'keyword':
            if action == 'add':
                if pulse.keywords_rel.count() >= 15:
                    return JsonResponse({'success': False, 'error': 'You cannot add more than 15 keywords.'}, status=400)
                category = (data.get('category') or '').strip()
                if not category:
                    first_cat = next(iter(pulse.categorized_keywords.keys()), 'Primary Discovery')
                    category = first_cat
                Keyword.objects.get_or_create(pulse=pulse, keyword=value, category=category)
            elif action == 'remove':
                Keyword.objects.filter(pulse=pulse, keyword=value).delete()
        elif item_type == 'buying_signal':
            if action == 'add':
                if pulse.buying_signals_rel.count() >= 15:
                    return JsonResponse({'success': False, 'error': 'You cannot add more than 15 buying signals.'}, status=400)
                category = (data.get('category') or '').strip()
                if not category:
                    first_cat = next(iter(pulse.categorized_buying_signals.keys()), 'Organizational')
                    category = first_cat
                BuyingSignal.objects.get_or_create(pulse=pulse, signal_name=value, category=category)
            elif action == 'remove':
                BuyingSignal.objects.filter(pulse=pulse, signal_name=value).delete()
        elif item_type == 'icp_metric':
            field = data.get('field')
            profile, _ = CompanyProfile.objects.get_or_create(pulse=pulse)
            
            # Backend validation: max must be strictly greater than min
            if field == 'revenue_range':
                matches = re.findall(r'(\d+(?:\.\d+)?)\s*([KkMmBb])?', str(value))
                if len(matches) >= 2:
                    unit_map = {'K': 1e3, 'M': 1e6, 'B': 1e9}
                    try:
                        min_dollars = float(matches[0][0]) * unit_map.get(matches[0][1].upper(), 1e6)
                        max_dollars = float(matches[1][0]) * unit_map.get(matches[1][1].upper(), 1e6)
                        if max_dollars <= min_dollars:
                            return JsonResponse({'success': False, 'error': 'Maximum revenue must be strictly greater than minimum revenue.'}, status=400)
                    except (ValueError, TypeError):
                        pass
                profile.revenue_range = value
            elif field in ('company_size', 'employee_count'):
                numbers = [int(n) for n in re.findall(r'\d+', str(value).replace(',', ''))]
                if len(numbers) >= 2 and numbers[1] <= numbers[0]:
                    label = 'Company size' if field == 'company_size' else 'Employee count'
                    return JsonResponse({'success': False, 'error': f'Maximum {label.lower()} must be strictly greater than minimum {label.lower()}.'}, status=400)
                if field == 'company_size':
                    profile.company_size = value
                else:
                    profile.employee_count = value
            else:
                return JsonResponse({'success': False, 'error': 'Invalid metric field'}, status=400)
            profile.save()
        else:
            return JsonResponse({'success': False, 'error': 'Invalid item type'}, status=400)
            
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
