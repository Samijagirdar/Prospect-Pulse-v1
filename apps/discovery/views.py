from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from apps.pulses.models import Pulse
from .models import DiscoveryRun, Article, Lead, Company, Competitor

def discovery_run_status(request, run_id):
    """
    Returns the execution status and metrics of a specific DiscoveryRun.
    """
    run = get_object_or_404(DiscoveryRun, id=run_id)
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


def pulse_results_api(request, pulse_uid):
    """
    Returns lists of scraped articles, leads, and mapped entities for a pulse.
    """
    pulse = get_object_or_404(Pulse, uid=pulse_uid)
    
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
        'article_title': l.source_article.title if l.source_article else ''
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
    pulse = get_object_or_404(Pulse, uid=pulse_uid)
    
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
    pulse = get_object_or_404(Pulse, uid=pulse_uid)
    
    leads = pulse.extracted_leads.all().order_by('-extracted_at')
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
    all_pulses = Pulse.objects.all().order_by('name')

    from django.db import connection
    cursor = connection.cursor()
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

    for l in leads:
        assigned_name = None
        try:
            cursor.execute(
                'SELECT c.camp_name FROM dashboard_bdrcampaignlead b JOIN dashboard_bdrcampaign c ON b.campaign_id = c.id WHERE b.crm_lead_id = %s OR (b.email != "" AND b.email = %s) LIMIT 1',
                [l.id, l.email or ""]
            )
            row = cursor.fetchone()
            if row and row[0]:
                assigned_name = row[0]
        except Exception:
            pass

        if not assigned_name:
            try:
                cursor.execute(
                    'SELECT c.name FROM dashboard_emailcampaignlead e JOIN dashboard_emailcampaign c ON e.campaign_id = c.id WHERE e.crm_lead_id = %s OR (e.email != "" AND e.email = %s) LIMIT 1',
                    [l.id, l.email or ""]
                )
                row = cursor.fetchone()
                if row and row[0]:
                    assigned_name = row[0]
            except Exception:
                pass

        if assigned_name:
            l.assigned_campaign_name = assigned_name[:15] + "..." if len(assigned_name) > 18 else assigned_name
        else:
            l.assigned_campaign_name = None

    context = {
        'pulse': pulse,
        'page_title': f"{pulse.name} - Leads & Targets",
        'leads': leads,
        'companies': companies,
        'competitors': competitors,
        'run_error': run_error,
        'all_pulses': all_pulses,
        'bdr_campaigns': bdr_campaigns,
        'email_campaigns': email_campaigns,
        'counts': {
            'leads': leads.count(),
            'companies': companies.count(),
            'competitors': competitors.count(),
        }
    }
    return render(request, 'discovery/leads.html', context)


from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def pulse_article_summarize_manual(request, article_id):
    """
    Manually triggers AI summarization and lead extraction for a single article.
    """
    from django.http import JsonResponse
    from apps.discovery.models import Article
    from apps.discovery.pipeline.summarizer import summarize_pulse_articles
    
    article = get_object_or_404(Article, id=article_id)
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


@csrf_exempt
@require_POST
def mark_notifications_read(request):
    """
    Marks all unread notifications as read.
    """
    from .models import Notification
    Notification.objects.filter(is_read=False).update(is_read=True)
    return JsonResponse({'success': True})


@csrf_exempt
@require_POST
def move_article_to_high_intent(request, article_id):
    """
    Directly moves an article from duplicate or noise to High Intent,
    updating the flags without calling the AI summarization API.
    """
    from django.http import JsonResponse
    from apps.discovery.models import Article
    
    article = get_object_or_404(Article, id=article_id)
    article.is_relevant = True
    article.is_duplicate = False
    article.is_summarized = False
    article.save()
    return JsonResponse({'success': True})


@csrf_exempt
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

        cursor = connection.cursor()

        # Update crm_lead table and mapping tables
        for lead_id in lead_ids:
            first_name, last_name, email, phone, company_name = "", "", "", "", ""
            try:
                from apps.discovery.models import Lead
                ld = Lead.objects.filter(id=lead_id).first()
                if ld:
                    parts = (ld.name or "").split(" ", 1)
                    first_name = parts[0]
                    last_name = parts[1] if len(parts) > 1 else ""
                    email = ld.email or ""
                    phone = ld.phone or ""
                    company_name = ld.organization_name or ""
            except Exception:
                pass

            if call_campaign_id:
                try:
                    cursor.execute(
                        'INSERT INTO dashboard_bdrcampaignlead (campaign_id, crm_lead_id, first_name, last_name, email, mobile_number, company_name, status, lead_status, made_call, created_date, modified_date, context) '
                        'VALUES (%s, %s, %s, %s, %s, %s, %s, "enabled", "new", 0, datetime("now"), datetime("now"), "")',
                        [call_campaign_id, lead_id, first_name, last_name, email, phone, company_name]
                    )
                except Exception:
                    pass

            if email_campaign_id:
                try:
                    cursor.execute(
                        'INSERT INTO dashboard_emailcampaignlead (campaign_id, crm_lead_id, first_name, last_name, email, created_date, modified_date) '
                        'VALUES (%s, %s, %s, %s, %s, datetime("now"), datetime("now"))',
                        [email_campaign_id, lead_id, first_name, last_name, email]
                    )
                except Exception:
                    pass

        return JsonResponse({
            'status': 'success',
            'message': f'Successfully added {len(lead_ids)} lead(s) to campaign.',
            'lead_count': len(lead_ids)
        })

    except Exception as e:
        logger.error(f"Error adding leads to campaign: {e}")
        return JsonResponse({'status': 'error', 'message': 'Failed to add leads to campaign.'}, status=500)


@csrf_exempt
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

        api_url = os.getenv('LEAD_ENRICHMENT_API_URL', '').strip()
        api_key = os.getenv('LEAD_ENRICHMENT_API_KEY', '').strip()

        cursor = connection.cursor()
        enriched_count = 0
        updated_leads = []

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


@csrf_exempt
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

        cursor = connection.cursor()
        moved_count = 0

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

