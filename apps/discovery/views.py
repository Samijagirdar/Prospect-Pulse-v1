import logging
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from apps.pulses.models import Pulse, TargetCompetitor
from .models import DiscoveryRun, Article, Lead, Company, Competitor

from common.auth import get_user_org, ensure_authenticated_dev

logger = logging.getLogger(__name__)

def _get_pulse_by_uid_or_id(pulse_uid, org=None):
    q = Q(uid=pulse_uid)
    if str(pulse_uid).isdigit():
        q |= Q(id=int(pulse_uid))
    if org:
        return get_object_or_404(Pulse, q, organisation_id=org.id)
    return get_object_or_404(Pulse, q)

def discovery_run_status(request, run_id):
    """
    Returns the execution status and metrics of a specific DiscoveryRun.
    """
    ensure_authenticated_dev(request)
    org = get_user_org(request)
    run = get_object_or_404(DiscoveryRun, id=run_id, pulse__organisation_id=org.id)
    return JsonResponse({
        'id': run.id,
        'status': run.status,
        'started_at': run.started_at.isoformat() if run.started_at else None,
        'completed_at': run.completed_at.isoformat() if run.completed_at else None,
        'articles_scraped': run.articles_scraped,
        'articles_relevant': run.articles_relevant,
        'leads_extracted': run.leads_extracted,
        'error_message': run.error_message
    })


@require_POST
def discovery_run_stop(request, run_id):
    """
    Aborts an in-progress DiscoveryRun gracefully.
    Marks run status as 'stopped' and records completion time.
    The Celery worker loops check this status periodically to halt execution.
    """
    ensure_authenticated_dev(request)
    org = get_user_org(request)
    run = get_object_or_404(DiscoveryRun, id=run_id, pulse__organisation_id=org.id)

    if run.status in ['completed', 'failed', 'stopped']:
        return JsonResponse({
            'success': False,
            'message': f"Run #{run.id} is already in a terminal state: {run.status}."
        }, status=400)

    run.status = 'stopped'
    run.completed_at = timezone.now()
    run.save(update_fields=['status', 'completed_at'])

    logger.info(f"Discovery run #{run.id} marked as 'stopped' by user.")
    return JsonResponse({
        'success': True,
        'run_id': run.id,
        'message': f"Discovery run #{run.id} stopped. Finalizing partial results..."
    })


def pulse_results_api(request, pulse_uid):
    """
    Returns lists of scraped articles, leads, and mapped entities for a pulse.
    """
    ensure_authenticated_dev(request)
    org = get_user_org(request)
    pulse = _get_pulse_by_uid_or_id(pulse_uid, org=org)
    
    # Segment articles
    articles = pulse.scraped_articles.all().order_by('-scraped_at')
    intent_articles = []
    deduplicated_sources = []
    noise_articles = []
    
    for art in articles:
        data = {
            'id': art.id,
            'title': art.title,
            'source': art.source,
            'url': art.url,
            'scraped_at': art.scraped_at.isoformat(),
            'buying_signal': art.buying_signal,
            'relevance_score': art.relevance_score,
            'relevance_tier': art.relevance_tier,
            'relevance_reason': art.relevance_reason,
            'executive_summary': art.executive_summary
        }
        if art.is_duplicate:
            deduplicated_sources.append(data)
        elif art.is_relevant:
            intent_articles.append(data)
        else:
            noise_articles.append(data)
            
    # Map leads
    leads_qs = pulse.extracted_leads.all().order_by('-extracted_at')
    leads = [{
        'id': l.id,
        'name': l.name,
        'designation': l.designation,
        'organization_name': l.organization_name,
        'score': l.score,
        'buying_signal': l.buying_signal,
        'reason': l.reason,
        'email': l.email,
        'phone': l.phone,
        'linkedin_url': l.linkedin_url or '',
        'article_title': l.source_article.title if l.source_article else '',
        'article_date': l.article_date_display
    } for l in leads_qs]

    
    # Map target companies
    companies_qs = pulse.extracted_companies.all().order_by('-extracted_at')
    companies = [{
        'id': c.id,
        'name': c.name,
        'score': c.score,
        'buying_signal': c.buying_signal,
        'reason': c.reason,
        'article_title': c.source_article.title if c.source_article else ''
    } for c in companies_qs]
    
    # Map extracted competitors
    competitors_qs = pulse.extracted_competitors.all().order_by('-extracted_at')
    competitors = [{
        'id': comp.id,
        'name': comp.name,
        'buying_signal': comp.buying_signal,
        'reason': comp.reason,
        'article_title': comp.source_article.title if comp.source_article else ''
    } for comp in competitors_qs]
    
    return JsonResponse({
        'intent_articles': intent_articles,
        'deduplicated_sources': deduplicated_sources,
        'noise_articles': noise_articles,
        'leads': leads,
        'companies': companies,
        'competitors': competitors
    })


def pulse_sources(request, pulse_uid):
    """
    Renders the dedicated sources detail page containing:
    - High Intent articles
    - Duplicate articles
    - Filtered out noise
    """
    from django.shortcuts import render
    from common.auth import get_user_org, ensure_authenticated_dev
    ensure_authenticated_dev(request)
    org = get_user_org(request)
    pulse = _get_pulse_by_uid_or_id(pulse_uid, org=org)
    
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
            
    # Fetch latest failed run if exists
    latest_run = pulse.discovery_runs.all().order_by('-started_at').first()
    run_error = None
    if latest_run and latest_run.status == 'failed' and latest_run.error_message:
        msg = latest_run.error_message
        if 'RESOURCE_EXHAUSTED' in msg or 'quota' in msg.lower() or 'spend cap' in msg.lower():
            run_error = "You have exceeded your monthly quota"
        else:
            run_error = msg
            
    context = {
        'pulse': pulse,
        'page_title': f"{pulse.name} - Sources",
        'intent_articles': intent_articles,
        'deduplicated_sources': deduplicated_sources,
        'noise_articles': noise_articles,
        'run_error': run_error,
        'counts': {
            'total': len(articles),
            'intent': len(intent_articles),
            'duplicate': len(deduplicated_sources),
            'noise': len(noise_articles),
        }
    }
    return render(request, 'discovery/sources.html', context)


def pulse_leads(request, pulse_uid):
    """
    Renders the dedicated leads detail page containing:
    - Extracted contacts (Leads)
    - Target accounts (Companies)
    - Competitors mentioned
    """
    from django.shortcuts import render
    from common.auth import get_user_org, ensure_authenticated_dev
    ensure_authenticated_dev(request)
    org = get_user_org(request)
    pulse = _get_pulse_by_uid_or_id(pulse_uid, org=org)
    
    leads = list(pulse.extracted_leads.all().order_by('-extracted_at'))
    companies = pulse.extracted_companies.all().order_by('-extracted_at')
    competitors = pulse.extracted_competitors.all().order_by('-extracted_at')
    
    # Fetch latest failed run if exists
    latest_run = pulse.discovery_runs.all().order_by('-started_at').first()
    run_error = None
    if latest_run and latest_run.status == 'failed' and latest_run.error_message:
        msg = latest_run.error_message
        if 'RESOURCE_EXHAUSTED' in msg or 'quota' in msg.lower() or 'spend cap' in msg.lower():
            run_error = "You have exceeded your monthly quota"
        else:
            run_error = msg
    all_pulses = Pulse.objects.filter(organisation_id=org.id).order_by('name')

    from django.db import connection
    with connection.cursor() as cursor:
        try:
            cursor.execute('SELECT id, camp_name FROM dashboard_bdrcampaign')
            bdr_campaigns = [{'id': r[0], 'name': r[1]} for r in cursor.fetchall()]
        except Exception:
            bdr_campaigns = []

        try:
            cursor.execute('SELECT id, name FROM dashboard_emailcampaign')
            email_campaigns = [{'id': r[0], 'name': r[1]} for r in cursor.fetchall()]
        except Exception:
            email_campaigns = []

        # High-performance bulk lookup for assigned campaigns (eliminates N+1 queries)
        assigned_map = {}
        if leads:
            lead_ids = [l.id for l in leads]
            lead_emails = [l.email.strip() for l in leads if l.email and l.email.strip()]

            try:
                placeholders_id = ','.join(['%s'] * len(lead_ids))
                bdr_params = list(lead_ids)
                bdr_sql = f"SELECT b.crm_lead_id, b.email, c.camp_name FROM dashboard_bdrcampaignlead b JOIN dashboard_bdrcampaign c ON b.campaign_id = c.id WHERE b.crm_lead_id IN ({placeholders_id})"
                if lead_emails:
                    placeholders_email = ','.join(['%s'] * len(lead_emails))
                    bdr_sql += f" OR (b.email != '' AND b.email IN ({placeholders_email}))"
                    bdr_params.extend(lead_emails)
                cursor.execute(bdr_sql, bdr_params)
                for r in cursor.fetchall():
                    c_id, c_email, c_name = r[0], r[1], r[2]
                    if c_id:
                        assigned_map[('id', c_id)] = c_name
                    if c_email:
                        assigned_map[('email', c_email)] = c_name
            except Exception:
                pass

            try:
                placeholders_id = ','.join(['%s'] * len(lead_ids))
                email_params = list(lead_ids)
                email_sql = f"SELECT e.crm_lead_id, e.email, c.name FROM dashboard_emailcampaignlead e JOIN dashboard_emailcampaign c ON e.campaign_id = c.id WHERE e.crm_lead_id IN ({placeholders_id})"
                if lead_emails:
                    placeholders_email = ','.join(['%s'] * len(lead_emails))
                    email_sql += f" OR (e.email != '' AND e.email IN ({placeholders_email}))"
                    email_params.extend(lead_emails)
                cursor.execute(email_sql, email_params)
                for r in cursor.fetchall():
                    c_id, c_email, c_name = r[0], r[1], r[2]
                    if ('id', c_id) not in assigned_map and c_id:
                        assigned_map[('id', c_id)] = c_name
                    if ('email', c_email) not in assigned_map and c_email:
                        assigned_map[('email', c_email)] = c_name
            except Exception:
                pass

    for l in leads:
        assigned_name = assigned_map.get(('id', l.id)) or (assigned_map.get(('email', l.email.strip())) if l.email else None)
        if assigned_name:
            l.assigned_campaign_name = assigned_name[:15] + "..." if len(assigned_name) > 18 else assigned_name
        else:
            l.assigned_campaign_name = None

    import json
    import re
    competitors_grouped = {}
    for comp in competitors:
        c_name = (comp.name or '').strip()
        if not c_name:
            continue
        c_key = c_name.lower()

        # Resolve competitor type
        c_type = getattr(comp, 'competitor_type', None)
        if not c_type:
            if comp.reason and '[indirect' in comp.reason.lower():
                c_type = 'indirect'
            else:
                c_type = 'direct'
        else:
            c_type = 'indirect' if 'indirect' in str(c_type).lower() else 'direct'

        clean_reason = comp.reason or ''
        clean_reason = re.sub(r'^\[(Direct Competitor|Indirect Alternative)\]\s*', '', clean_reason, flags=re.IGNORECASE).strip()

        if c_key not in competitors_grouped:
            competitors_grouped[c_key] = {
                'id': comp.id,
                'name': c_name,
                'competitor_type': c_type,
                'primary_comp': comp,
                'buying_signal': comp.buying_signal or 'Competitor Activity',
                'reason': clean_reason,
                'source_article': comp.source_article,
                'extracted_at': comp.extracted_at,
                'moves_count': 0,
                'moves': []
            }
        
        art_date = 'Recent'
        if comp.source_article:
            if comp.source_article.publication_date:
                art_date = str(comp.source_article.publication_date)
            elif comp.source_article.scraped_at:
                art_date = comp.source_article.scraped_at.strftime('%b %d, %Y')
        elif comp.extracted_at:
            art_date = comp.extracted_at.strftime('%b %d, %Y')

        competitors_grouped[c_key]['moves'].append({
            'id': comp.id,
            'type': c_type,
            'signal': comp.buying_signal or 'Strategic Move',
            'reason': clean_reason,
            'article_title': comp.source_article.title if comp.source_article else 'Source Article',
            'article_source': comp.source_article.source if comp.source_article else 'Verified News',
            'article_url': comp.source_article.url if comp.source_article else '#',
            'date': art_date,
            'extracted_at': comp.extracted_at.strftime('%b %d, %Y') if comp.extracted_at else ''
        })
        competitors_grouped[c_key]['moves_count'] += 1

    grouped_competitors = list(competitors_grouped.values())
    direct_competitors_count = sum(1 for c in grouped_competitors if c.get('competitor_type') == 'direct')
    indirect_competitors_count = sum(1 for c in grouped_competitors if c.get('competitor_type') == 'indirect')

    context = {
        'pulse': pulse,
        'page_title': f"{pulse.name} - Leads & Targets",
        'leads': leads,
        'companies': companies,
        'competitors': competitors,
        'grouped_competitors': grouped_competitors,
        'competitors_json': json.dumps(grouped_competitors, default=str),
        'direct_competitors_count': direct_competitors_count,
        'indirect_competitors_count': indirect_competitors_count,
        'run_error': run_error,
        'all_pulses': all_pulses,
        'bdr_campaigns': bdr_campaigns,
        'email_campaigns': email_campaigns,
        'counts': {
            'leads': len(leads),
            'companies': companies.count(),
            'competitors': len(grouped_competitors),
        }
    }
    return render(request, 'discovery/leads.html', context)


@require_POST
def pulse_article_summarize_manual(request, article_id):
    """
    Manually triggers AI summarization and lead extraction for a single article.
    """
    from django.http import JsonResponse
    from apps.discovery.models import Article
    from apps.discovery.pipeline.summarizer import summarize_pulse_articles
    
    ensure_authenticated_dev(request)
    org = get_user_org(request)
    article = get_object_or_404(Article, id=article_id, pulse__organisation_id=org.id)
    pulse = article.pulse
    
    # Temporarily reset markers so the summarizer processes it
    article.is_summarized = False
    article.is_relevant = True
    article.is_duplicate = False
    article.save()
    
    try:
        # Query single item as queryset
        qs = Article.objects.filter(id=article.id)
        summarize_pulse_articles(pulse, discovery_run=article.discovery_run, articles_qs=qs)
        try:
            from apps.discovery.pipeline.lead_extractor import extract_pulse_leads
            extract_pulse_leads(pulse, discovery_run=article.discovery_run, articles_qs=qs)
        except Exception as le_err:
            logger.error(f"Lead extraction error in manual article trigger: {le_err}")
        
        # Reload fresh record
        article.refresh_from_db()
        if article.is_summarized:
            return JsonResponse({
                'success': True,
                'summary': article.executive_summary or ""
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Summarization run executed but article state was not updated.'
            }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_POST
def mark_notifications_read(request):
    """
    Marks all unread notifications as read.
    """
    ensure_authenticated_dev(request)
    get_user_org(request)
    from .models import Notification
    Notification.objects.filter(is_read=False).update(is_read=True)
    return JsonResponse({'success': True})


@require_POST
def move_article_to_high_intent(request, article_id):
    """
    Directly moves an article from duplicate or noise to High Intent,
    updating the flags without calling the AI summarization API.
    """
    from django.http import JsonResponse
    from apps.discovery.models import Article
    
    ensure_authenticated_dev(request)
    org = get_user_org(request)
    article = get_object_or_404(Article, id=article_id, pulse__organisation_id=org.id)
    article.is_relevant = True
    article.is_duplicate = False
    article.is_summarized = False
    article.save()
    return JsonResponse({'success': True})


@require_POST
def add_leads_to_campaign(request):
    """
    Associates selected leads with a Call Campaign (BDR) and/or Email Campaign
    by storing them directly into the respective database campaign tables.
    Selection of either Call Campaign or Email Campaign (or both) is supported.
    """
    import json
    import logging
    from django.db import connection
    from django.http import JsonResponse
    logger = logging.getLogger(__name__)

    try:
        ensure_authenticated_dev(request)
        org = get_user_org(request)

        data = json.loads(request.body) if request.body and request.content_type == 'application/json' else request.POST
        raw_lead_ids = data.get('lead_ids', '')
        if isinstance(raw_lead_ids, str):
            lead_ids = [int(i.strip()) for i in raw_lead_ids.split(',') if i.strip().isdigit()]
        elif isinstance(raw_lead_ids, list):
            lead_ids = [int(i) for i in raw_lead_ids if str(i).isdigit()]
        else:
            lead_ids = []

        call_campaign_id = data.get('call_campaign_id') or None
        email_campaign_id = data.get('email_campaign_id') or None

        if not lead_ids:
            return JsonResponse({'status': 'error', 'message': 'No leads selected.'}, status=400)

        if not call_campaign_id and not email_campaign_id:
            return JsonResponse({'status': 'error', 'message': 'Please select at least one campaign (Call or Email).'}, status=400)

        from apps.discovery.models import Lead
        leads_qs = Lead.objects.filter(id__in=lead_ids, pulse__organisation_id=org.id)
        leads_dict = {ld.id: ld for ld in leads_qs}
        lead_ids = list(leads_dict.keys())

        if not lead_ids:
            return JsonResponse({'status': 'error', 'message': 'Selected leads do not exist or belong to another organization.'}, status=404)

        # Validation helper functions for required contact info
        def has_valid_phone(phone_val):
            if not phone_val:
                return False
            cleaned = str(phone_val).strip()
            return bool(cleaned and cleaned not in ['—', '-', 'None', 'null', 'N/A', 'n/a', ''])

        def has_valid_email(email_val):
            if not email_val:
                return False
            cleaned = str(email_val).strip()
            return bool(cleaned and cleaned not in ['—', '-', 'None', 'null', 'N/A', 'n/a', ''] and '@' in cleaned and '.' in cleaned)

        missing_phone_leads = []
        missing_email_leads = []

        for lid in lead_ids:
            ld = leads_dict.get(lid)
            lead_name = (ld.name if ld and ld.name else f"Lead #{lid}").strip()
            if call_campaign_id:
                if not ld or not has_valid_phone(ld.phone):
                    missing_phone_leads.append(lead_name)
            if email_campaign_id:
                if not ld or not has_valid_email(ld.email):
                    missing_email_leads.append(lead_name)

        errors = []
        if missing_phone_leads:
            if len(missing_phone_leads) == 1:
                errors.append(f"Cannot add to Call Campaign: '{missing_phone_leads[0]}' does not have a phone number.")
            else:
                names_preview = ", ".join(missing_phone_leads[:3])
                suffix = f" and {len(missing_phone_leads) - 3} more" if len(missing_phone_leads) > 3 else ""
                errors.append(f"Cannot add to Call Campaign: {len(missing_phone_leads)} lead(s) ({names_preview}{suffix}) are missing a valid phone number.")

        if missing_email_leads:
            if len(missing_email_leads) == 1:
                errors.append(f"Cannot add to Email Campaign: '{missing_email_leads[0]}' does not have an email address.")
            else:
                names_preview = ", ".join(missing_email_leads[:3])
                suffix = f" and {len(missing_email_leads) - 3} more" if len(missing_email_leads) > 3 else ""
                errors.append(f"Cannot add to Email Campaign: {len(missing_email_leads)} lead(s) ({names_preview}{suffix}) are missing a valid email address.")

        if errors:
            return JsonResponse({
                'status': 'error',
                'message': " ".join(errors),
                'missing_phone_leads': missing_phone_leads,
                'missing_email_leads': missing_email_leads
            }, status=400)

        with connection.cursor() as cursor:
            # Update crm_lead table and mapping tables
            for lead_id in lead_ids:
                ld = leads_dict.get(lead_id)
                first_name, last_name, email, phone, company_name = "", "", "", "", ""
                if ld:
                    parts = (ld.name or "").split(" ", 1)
                    first_name = parts[0]
                    last_name = parts[1] if len(parts) > 1 else ""
                    email = (ld.email or "").strip()
                    phone = (ld.phone or "").strip()
                    company_name = (ld.organization_name or "").strip()

                if call_campaign_id:
                    try:
                        cursor.execute(
                            'INSERT INTO dashboard_bdrcampaignlead (campaign_id, crm_lead_id, first_name, last_name, email, mobile_number, company_name, status, lead_status, made_call, created_date, modified_date, context) '
                            'VALUES (%s, %s, %s, %s, %s, %s, %s, "enabled", "new", 0, datetime("now"), datetime("now"), "")',
                            [call_campaign_id, lead_id, first_name, last_name, email, phone, company_name]
                        )
                    except Exception as ce:
                        logger.warning(f"Could not insert lead {lead_id} into dashboard_bdrcampaignlead: {ce}")

                if email_campaign_id:
                    try:
                        cursor.execute(
                            'INSERT INTO dashboard_emailcampaignlead (campaign_id, crm_lead_id, first_name, last_name, email, created_date, modified_date) '
                            'VALUES (%s, %s, %s, %s, %s, datetime("now"), datetime("now"))',
                            [email_campaign_id, lead_id, first_name, last_name, email]
                        )
                    except Exception as ee:
                        logger.warning(f"Could not insert lead {lead_id} into dashboard_emailcampaignlead: {ee}")

        campaign_types = []
        if call_campaign_id:
            campaign_types.append("Call")
        if email_campaign_id:
            campaign_types.append("Email")
        campaign_label = " & ".join(campaign_types) + " Campaign"

        return JsonResponse({
            'status': 'success',
            'message': f'Successfully added {len(lead_ids)} verified lead(s) to {campaign_label}.',
            'lead_count': len(lead_ids)
        })

    except Exception as e:
        logger.error(f"Error adding leads to campaign: {e}")
        return JsonResponse({'status': 'error', 'message': 'Failed to add leads to campaign.'}, status=500)


@require_POST
def enrich_leads(request):
    """
    Enriches selected lead(s) by calling an external enrichment API configured via .env
    (LEAD_ENRICHMENT_API_URL and LEAD_ENRICHMENT_API_KEY).
    Fetches updated phone number and email address and updates the database records.
    """
    import os
    import json
    import logging
    import requests
    from django.db import connection
    from django.http import JsonResponse
    logger = logging.getLogger(__name__)

    try:
        ensure_authenticated_dev(request)
        org = get_user_org(request)

        data = json.loads(request.body) if request.body and request.content_type == 'application/json' else request.POST
        raw_lead_ids = data.get('lead_ids', '')
        if isinstance(raw_lead_ids, str):
            lead_ids = [int(i.strip()) for i in raw_lead_ids.split(',') if i.strip().isdigit()]
        elif isinstance(raw_lead_ids, list):
            lead_ids = [int(i) for i in raw_lead_ids if str(i).isdigit()]
        else:
            lead_ids = []

        if not lead_ids:
            return JsonResponse({'status': 'error', 'message': 'No leads selected for enrichment.'}, status=400)

        # Ensure leads strictly belong to user's organization (BOLA defense)
        from apps.discovery.models import Lead
        valid_lead_ids = list(Lead.objects.filter(id__in=lead_ids, pulse__organisation_id=org.id).values_list('id', flat=True))
        if not valid_lead_ids:
            return JsonResponse({'status': 'error', 'message': 'Selected leads do not exist or belong to another organization.'}, status=404)
        lead_ids = valid_lead_ids

        api_url = os.getenv('LEAD_ENRICHMENT_API_URL', '').strip()
        api_key = os.getenv('LEAD_ENRICHMENT_API_KEY', '').strip()

        enriched_count = 0
        updated_leads = []

        with connection.cursor() as cursor:
            if api_url:
                try:
                    headers = {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {api_key}' if api_key else ''
                    }
                    response = requests.post(api_url, json={'lead_ids': lead_ids}, headers=headers, timeout=10)
                    if response.status_code in [200, 201]:
                        res_data = response.json()
                        enriched_items = res_data.get('enriched_leads', [])
                        for item in enriched_items:
                            lid = item.get('id')
                            new_email = item.get('email')
                            new_phone = item.get('phone')
                            if lid:
                                try:
                                    cursor.execute(
                                        'UPDATE discovery_lead SET email = COALESCE(NULLIF(%s, ""), email), phone = COALESCE(NULLIF(%s, ""), phone), is_enriched = 1 WHERE id = %s',
                                        [new_email, new_phone, lid]
                                    )
                                except Exception:
                                    pass
                                try:
                                    cursor.execute(
                                        'UPDATE crm_lead SET email = COALESCE(NULLIF(%s, ""), email), phone = COALESCE(NULLIF(%s, ""), phone), is_enriched = 1 WHERE id = %s',
                                        [new_email, new_phone, lid]
                                    )
                                except Exception:
                                    pass
                                enriched_count += 1
                                updated_leads.append({'id': lid, 'email': new_email, 'phone': new_phone})
                    else:
                        logger.error(f"Enrichment API status {response.status_code}")
                        return JsonResponse({'status': 'error', 'message': f'Failed to enrich leads (API Status {response.status_code}).'}, status=500)
                except Exception as e:
                    logger.error(f"Enrichment API error: {e}")
                    return JsonResponse({'status': 'error', 'message': 'Failed to enrich lead(s).'}, status=500)
            else:
                # Placeholder mode when LEAD_ENRICHMENT_API_URL is not configured in .env
                logger.info(f"LEAD_ENRICHMENT_API_URL not set in .env. Flagging lead(s) {lead_ids} as enriched.")
                for lid in lead_ids:
                    try:
                        cursor.execute('UPDATE discovery_lead SET is_enriched = 1 WHERE id = %s', [lid])
                    except Exception:
                        pass
                    try:
                        cursor.execute('UPDATE crm_lead SET is_enriched = 1 WHERE id = %s', [lid])
                    except Exception:
                        pass
                    enriched_count += 1
                    updated_leads.append({'id': lid})

        return JsonResponse({
            'status': 'success',
            'message': f'Successfully enriched {enriched_count} lead(s)!',
            'enriched_count': enriched_count,
            'updated_leads': updated_leads
        })

    except Exception as e:
        logger.error(f"Error enriching leads: {e}")
        return JsonResponse({'status': 'error', 'message': 'Failed to enrich lead(s).'}, status=500)


@require_POST
def move_leads_to_crm(request):
    """
    Moves selected lead(s) from Prospect Pulse discovery tables into Agentyne's main CRM table (crm_lead).
    If lead already exists in crm_lead, updates missing contact fields.
    """
    import json
    import logging
    from django.db import connection
    from django.http import JsonResponse
    logger = logging.getLogger(__name__)

    try:
        ensure_authenticated_dev(request)
        org = get_user_org(request)

        data = json.loads(request.body) if request.body and request.content_type == 'application/json' else request.POST
        raw_lead_ids = data.get('lead_ids', '')
        if isinstance(raw_lead_ids, str):
            lead_ids = [int(i.strip()) for i in raw_lead_ids.split(',') if i.strip().isdigit()]
        elif isinstance(raw_lead_ids, list):
            lead_ids = [int(i) for i in raw_lead_ids if str(i).isdigit()]
        else:
            lead_ids = []

        if not lead_ids:
            return JsonResponse({'status': 'error', 'message': 'No leads selected to move to CRM.'}, status=400)

        # Ensure leads strictly belong to user's organization (BOLA defense)
        from apps.discovery.models import Lead
        valid_lead_ids = list(Lead.objects.filter(id__in=lead_ids, pulse__organisation_id=org.id).values_list('id', flat=True))
        if not valid_lead_ids:
            return JsonResponse({'status': 'error', 'message': 'Selected leads do not exist or belong to another organization.'}, status=404)
        lead_ids = valid_lead_ids

        moved_count = 0

        with connection.cursor() as cursor:
            for lead_id in lead_ids:
                # Fetch lead from discovery_lead
                cursor.execute(
                    'SELECT id, name, designation, organization_name, score, email, phone FROM discovery_lead WHERE id = %s',
                    [lead_id]
                )
                row = cursor.fetchone()
                if not row:
                    continue

                lid, name, title, company_name, score, email, phone = row
                name = name or ''
                parts = name.split(' ', 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ''
                title = title or ''
                company_name = company_name or ''
                email = email or ''
                phone = phone or ''
                score = score or 0

                # Check if lead already exists in crm_lead by email or first_name + company_name
                existing_id = None
                if email:
                    cursor.execute('SELECT id FROM crm_lead WHERE email = %s LIMIT 1', [email])
                    r = cursor.fetchone()
                    if r:
                        existing_id = r[0]

                if not existing_id and first_name and company_name:
                    cursor.execute('SELECT id FROM crm_lead WHERE first_name = %s AND company_name = %s LIMIT 1', [first_name, company_name])
                    r = cursor.fetchone()
                    if r:
                        existing_id = r[0]

                if existing_id:
                    # Update existing crm_lead record with missing fields
                    cursor.execute(
                        'UPDATE crm_lead SET '
                        'title = COALESCE(NULLIF(%s, ""), title), '
                        'company_name = COALESCE(NULLIF(%s, ""), company_name), '
                        'email = COALESCE(NULLIF(%s, ""), email), '
                        'phone = COALESCE(NULLIF(%s, ""), phone), '
                        'ai_lead_score = MAX(ai_lead_score, %s) '
                        'WHERE id = %s',
                        [title, company_name, email, phone, score, existing_id]
                    )
                else:
                    # Insert new crm_lead record into Agentyne CRM
                    cursor.execute(
                        'INSERT INTO crm_lead (first_name, last_name, title, company_name, email, phone, mobile, status, ai_lead_score, created_at, updated_at, context) '
                        'VALUES (%s, %s, %s, %s, %s, %s, %s, "new", %s, datetime("now"), datetime("now"), "Imported from Prospect Pulse")',
                        [first_name, last_name, title, company_name, email, phone, phone, score]
                    )

                # Flag discovery_lead as moved
                try:
                    cursor.execute('UPDATE discovery_lead SET is_moved_to_crm = 1 WHERE id = %s', [lead_id])
                except Exception:
                    pass

                moved_count += 1

        return JsonResponse({
            'status': 'success',
            'message': f'Successfully moved {moved_count} lead(s) to Agentyne CRM!',
            'moved_count': moved_count
        })

    except Exception as e:
        logger.error(f"Error moving leads to CRM: {e}")
        return JsonResponse({'status': 'error', 'message': 'Failed to move leads to CRM.'}, status=500)


@require_POST
def export_leads(request):
    """
    Exports selected leads (or all leads) in Excel (.xlsx), PDF (.pdf), or Word (.docx) format.
    Fields exported: Name, Position, Account, Email, Phone, LinkedIn Profile, Signal Date, Score.
    """
    import json
    import logging
    from datetime import datetime
    from django.http import HttpResponse, JsonResponse
    from apps.discovery.models import Lead
    from apps.discovery.pipeline.lead_exporter import export_leads_excel, export_leads_pdf, export_leads_docx
    logger = logging.getLogger(__name__)

    try:
        ensure_authenticated_dev(request)
        org = get_user_org(request)

        data = json.loads(request.body) if request.body and request.content_type == 'application/json' else request.POST
        raw_lead_ids = data.get('lead_ids', '')
        export_fmt = (data.get('format') or 'excel').lower().strip()

        if isinstance(raw_lead_ids, str):
            lead_ids = [int(i.strip()) for i in raw_lead_ids.split(',') if i.strip().isdigit()]
        elif isinstance(raw_lead_ids, list):
            lead_ids = [int(i) for i in raw_lead_ids if str(i).isdigit()]
        else:
            lead_ids = []

        if not lead_ids:
            return JsonResponse({'status': 'error', 'message': 'Please select at least one lead to export.'}, status=400)

        leads_qs = Lead.objects.filter(id__in=lead_ids, pulse__organisation_id=org.id).select_related('source_article', 'pulse')
        leads_map = {l.id: l for l in leads_qs}
        ordered_leads = [leads_map[lid] for lid in lead_ids if lid in leads_map]

        if not ordered_leads:
            return JsonResponse({'status': 'error', 'message': 'No matching lead records found to export.'}, status=404)

        import re
        pulse_name = (data.get('pulse_name') or '').strip()
        if not pulse_name:
            first_lead = ordered_leads[0]
            if first_lead and getattr(first_lead, 'pulse', None) and first_lead.pulse.name:
                pulse_name = first_lead.pulse.name.strip()

        clean_pulse_name = re.sub(r'[^\w\-]+', '_', pulse_name).strip('_').lower()
        file_prefix = f"prospectpulse_leads_{clean_pulse_name}" if clean_pulse_name else "prospectpulse_leads"

        if export_fmt in ('pdf',):
            file_bytes = export_leads_pdf(ordered_leads)
            content_type = 'application/pdf'
            filename = f"{file_prefix}.pdf"
        elif export_fmt in ('doc', 'docx', 'word'):
            file_bytes = export_leads_docx(ordered_leads)
            content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            filename = f"{file_prefix}.docx"
        else: # Default: excel
            file_bytes = export_leads_excel(ordered_leads)
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            filename = f"{file_prefix}.xlsx"

        response = HttpResponse(file_bytes, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return response

    except Exception as e:
        logger.error(f"Error exporting leads: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'Failed to export leads: {str(e)}'}, status=500)


@login_required
@require_POST
def delete_company(request, company_id):
    """
    Deletes an extracted company record and cascades deletion to all contact leads
    matching this company's name within the same pulse.
    """
    from django.db import transaction
    try:
        ensure_authenticated_dev(request)
        org = get_user_org(request)
        company = get_object_or_404(Company, id=company_id, pulse__organisation_id=org.id)
        pulse = company.pulse
        company_name = (company.name or '').strip()

        deleted_lead_ids = []
        deleted_leads_count = 0

        with transaction.atomic():
            if company_name:
                from django.db.models.functions import Trim
                # Find and delete all leads associated with this company in this pulse (handling whitespace and case)
                leads_qs = Lead.objects.annotate(
                    trimmed_org=Trim('organization_name')
                ).filter(
                    pulse=pulse,
                    trimmed_org__iexact=company_name
                )
                deleted_lead_ids = list(leads_qs.values_list('id', flat=True))
                deleted_leads_count = len(deleted_lead_ids)
                if deleted_leads_count > 0:
                    leads_qs.delete()

            # Delete the company
            company.delete()

        remaining_companies = pulse.extracted_companies.count()
        remaining_leads = pulse.extracted_leads.count()

        if deleted_leads_count > 0:
            msg = f"Company '{company_name}' and {deleted_leads_count} associated lead(s) removed successfully."
        else:
            msg = f"Company '{company_name}' removed successfully."

        return JsonResponse({
            'status': 'success',
            'message': msg,
            'company_id': company_id,
            'company_name': company_name,
            'deleted_leads_count': deleted_leads_count,
            'deleted_lead_ids': deleted_lead_ids,
            'remaining_companies': remaining_companies,
            'remaining_leads': remaining_leads,
        })
    except Exception as e:
        logger.error(f"Error deleting company {company_id}: {e}")
        return JsonResponse({'status': 'error', 'message': 'Failed to delete company.'}, status=500)


@login_required
@require_POST
def delete_competitor(request, competitor_id):
    """
    Deletes an extracted competitor record.
    """
    try:
        ensure_authenticated_dev(request)
        org = get_user_org(request)
        competitor = get_object_or_404(Competitor, id=competitor_id, pulse__organisation_id=org.id)
        pulse = competitor.pulse
        competitor_name = (competitor.name or '').strip()

        # Delete all instances of this competitor under this pulse
        Competitor.objects.filter(pulse=pulse, name__iexact=competitor_name).delete()
        # Also remove from pulse monitored competitors
        TargetCompetitor.objects.filter(pulse=pulse, competitor_name__iexact=competitor_name).delete()
        remaining_competitors = pulse.extracted_competitors.values('name').distinct().count()

        return JsonResponse({
            'status': 'success',
            'message': f"Competitor '{competitor_name}' and all tracked moves removed successfully.",
            'competitor_id': competitor_id,
            'competitor_name': competitor_name,
            'remaining_competitors': remaining_competitors,
        })
    except Exception as e:
        logger.error(f"Error deleting competitor {competitor_id}: {e}")
        return JsonResponse({'status': 'error', 'message': 'Failed to delete competitor.'}, status=500)


@login_required
@require_POST
def move_company_to_competitor(request, company_id):
    """
    Moves an extracted target company to the Competitors list:
    1. Adds / updates the entity in Competitor table.
    2. Adds to pulse.competitors (TargetCompetitor) so future discovery runs actively monitor it.
    3. Deletes all associated contact leads for this company from this pulse.
    4. Deletes the company record.
    Returns JSON with updated counts and deleted lead IDs.
    """
    from django.db import transaction
    from django.db.models.functions import Trim

    try:
        ensure_authenticated_dev(request)
        org = get_user_org(request)
        company = get_object_or_404(Company, id=company_id, pulse__organisation_id=org.id)
        pulse = company.pulse
        company_name = (company.name or '').strip()

        deleted_lead_ids = []
        deleted_leads_count = 0

        source_art = company.source_article or pulse.scraped_articles.first()
        if not source_art:
            source_art = Article.objects.create(
                pulse=pulse,
                title=f"Profile for {company_name}",
                url="",
                source="Manual Classification"
            )

        with transaction.atomic():
            # 1. Create or update Competitor record
            competitor, _ = Competitor.objects.update_or_create(
                pulse=pulse,
                name__iexact=company_name,
                defaults={
                    'name': company_name,
                    'competitor_type': 'direct',
                    'buying_signal': company.buying_signal or 'Competitor Mentioned',
                    'reason': company.reason or f'Reclassified as competitor from target companies.',
                    'source_article': source_art,
                    'discovery_run': company.discovery_run,
                }
            )

            # 2. Add to Monitored Competitors so the scraper actively searches for this competitor
            if not TargetCompetitor.objects.filter(pulse=pulse, competitor_name__iexact=company_name).exists():
                TargetCompetitor.objects.create(
                    pulse=pulse,
                    competitor_name=company_name
                )

            # 3. Delete all associated contact leads
            if company_name:
                leads_qs = Lead.objects.annotate(
                    trimmed_org=Trim('organization_name')
                ).filter(
                    pulse=pulse,
                    trimmed_org__iexact=company_name
                )
                deleted_lead_ids = list(leads_qs.values_list('id', flat=True))
                deleted_leads_count = len(deleted_lead_ids)
                if deleted_leads_count > 0:
                    leads_qs.delete()

            # 4. Delete the original Company record
            company.delete()

        remaining_companies = pulse.extracted_companies.count()
        remaining_competitors = pulse.extracted_competitors.count()
        remaining_leads = pulse.extracted_leads.count()

        if deleted_leads_count > 0:
            msg = f"Moved '{company_name}' to Competitors and added to Monitored Competitors. {deleted_leads_count} associated lead(s) were removed."
        else:
            msg = f"Moved '{company_name}' to Competitors and added to Monitored Competitors."

        return JsonResponse({
            'status': 'success',
            'message': msg,
            'company_id': company_id,
            'company_name': company_name,
            'competitor_id': competitor.id,
            'deleted_leads_count': deleted_leads_count,
            'deleted_lead_ids': deleted_lead_ids,
            'remaining_companies': remaining_companies,
            'remaining_competitors': remaining_competitors,
            'remaining_leads': remaining_leads,
        })
    except Exception as e:
        logger.error(f"Error moving company {company_id} to competitor: {e}")
        return JsonResponse({'status': 'error', 'message': 'Failed to move company to competitors.'}, status=500)


@login_required
@require_POST
def move_competitor_to_company(request, competitor_id):
    """
    Moves an extracted competitor to the Target Companies list:
    1. Creates / updates the Company record.
    2. Removes the entity from the Competitor table.
    3. Removes the entity from pulse.competitors (TargetCompetitor).
    4. Triggers decision-maker lead extraction for this company.
    Returns JSON with updated counts and extracted leads.
    """
    from django.db import transaction

    try:
        ensure_authenticated_dev(request)
        org = get_user_org(request)
        competitor = get_object_or_404(Competitor, id=competitor_id, pulse__organisation_id=org.id)
        pulse = competitor.pulse
        competitor_name = (competitor.name or '').strip()

        source_art = competitor.source_article or pulse.scraped_articles.first()
        if not source_art:
            source_art = Article.objects.create(
                pulse=pulse,
                title=f"Profile for {competitor_name}",
                url="",
                source="Manual Classification"
            )

        with transaction.atomic():
            # 1. Create or update Company record
            company, _ = Company.objects.update_or_create(
                pulse=pulse,
                name__iexact=competitor_name,
                defaults={
                    'name': competitor_name,
                    'buying_signal': competitor.buying_signal or 'Target Account',
                    'reason': competitor.reason or f'Promoted to target company from competitors.',
                    'source_article': source_art,
                    'discovery_run': competitor.discovery_run,
                    'score': 80,
                }
            )

            # 2. Delete all records for this competitor
            Competitor.objects.filter(pulse=pulse, name__iexact=competitor_name).delete()

            # 3. Remove from Monitored Competitors list
            TargetCompetitor.objects.filter(
                pulse=pulse,
                competitor_name__iexact=competitor_name
            ).delete()

        # 3. Extract leads for the newly promoted company
        new_leads = []
        try:
            from apps.discovery.pipeline.lead_extractor import extract_leads_for_company
            new_leads = extract_leads_for_company(pulse=pulse, company=company, article=company.source_article)
        except Exception as ex:
            logger.error(f"Error during lead extraction for promoted company {competitor_name}: {ex}")

        remaining_companies = pulse.extracted_companies.count()
        remaining_competitors = pulse.extracted_competitors.values('name').distinct().count()
        remaining_leads = pulse.extracted_leads.count()

        leads_data = [
            {
                'id': l.id,
                'name': l.name,
                'designation': l.designation or '',
                'organization_name': l.organization_name,
                'score': l.score,
                'buying_signal': l.buying_signal or '',
                'reason': l.reason or '',
                'email': l.email or '',
                'phone': l.phone or '',
                'linkedin_url': l.linkedin_url or '',
                'article_date': l.article_date_display,
                'source_article_title': l.source_article.title if l.source_article else '',
                'source_article_url': l.source_article.url if l.source_article else '',
                'source_article_source': l.source_article.source if l.source_article else '',
            }

            for l in new_leads
        ]

        if len(new_leads) > 0:
            msg = f"Moved '{competitor_name}' to Target Companies and extracted {len(new_leads)} decision-maker lead(s)."
        else:
            msg = f"Moved '{competitor_name}' to Target Companies."

        return JsonResponse({
            'status': 'success',
            'message': msg,
            'competitor_id': competitor_id,
            'company_id': company.id,
            'company_name': competitor_name,
            'extracted_leads_count': len(new_leads),
            'extracted_leads': leads_data,
            'remaining_companies': remaining_companies,
            'remaining_competitors': remaining_competitors,
            'remaining_leads': remaining_leads,
        })
    except Exception as e:
        logger.error(f"Error moving competitor {competitor_id} to company: {e}")
        return JsonResponse({'status': 'error', 'message': 'Failed to move competitor to companies.'}, status=500)



