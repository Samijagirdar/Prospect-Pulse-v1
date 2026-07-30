from django.http import JsonResponse
from django.shortcuts import get_object_or_404
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
            
    context = {
        'pulse': pulse,
        'page_title': f"{pulse.name} - Sources",
        'intent_articles': intent_articles,
        'deduplicated_sources': deduplicated_sources,
        'noise_articles': noise_articles,
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
    
    context = {
        'pulse': pulse,
        'page_title': f"{pulse.name} - Leads & Targets",
        'leads': leads,
        'companies': companies,
        'competitors': competitors,
        'counts': {
            'leads': leads.count(),
            'companies': companies.count(),
            'competitors': competitors.count(),
        }
    }
    return render(request, 'discovery/leads.html', context)
