import asyncio
from datetime import datetime, timedelta
from django.utils import timezone
from apps.pulses.models import Pulse
from .models import DiscoveryRun, Article, Lead
from .pipeline.scraper import GoogleNewsScraper
from .pipeline.deduplicator import Deduplicator
from .pipeline.summarizer import summarize_pulse_articles

def run_pulse_discovery(pulse_id, run_id=None):
    """
    Synchronous pipeline runner for executing a prospect pulse discovery scan.
    Calculates timeframe windows, scrapes articles, deduplicates, runs LLM judges,
    and extracts leads, target companies, and competitors.
    """
    pulse = Pulse.objects.get(id=pulse_id)
    
    # Initialize or fetch run log
    if run_id:
        run = DiscoveryRun.objects.get(id=run_id)
        run.status = 'starting'
        run.started_at = timezone.now()
        run.save()
    else:
        run = DiscoveryRun.objects.create(
            pulse=pulse,
            status='starting',
            started_at=timezone.now()
        )
    
    try:
        # Timeframe calculation (60 days back on first run, 2 days on subsequent runs)
        run.status = 'calculating query timeframe...'
        run.save()
        completed_runs = DiscoveryRun.objects.filter(pulse=pulse, status='completed')
        if not completed_runs.exists() or not pulse.last_processed_at:
            timeframe_days = 60
            print(f"First run for pulse '{pulse.name}'. Using historical time window of 60 days.")
        else:
            timeframe_days = 2
            print(f"Incremental run for pulse '{pulse.name}'. Using incremental time window of 2 days.")

        # Collect keywords
        keywords = [kw.keyword for kw in pulse.keywords_rel.all()]
        if not keywords:
            keywords = ["Revenue Intelligence Platform", "Sales Automation Software", "AI Lead Generation"]
            print("No keywords configured. Using default placeholder search terms.")

        # Initialize and configure scraper
        scraper = GoogleNewsScraper()
        search_config = {
            'hl': 'en-US',
            'gl': 'US',
            'pagination': 1
        }
        
        # Execute scraping query loops using a fresh event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        scraped_articles_data = []
        try:
            loop.run_until_complete(scraper.setup_browser())
            for i, query in enumerate(keywords):
                run.status = f'Scraping articles for keyword ({i+1}/{len(keywords)}): "{query}"'
                run.save()
                articles = loop.run_until_complete(
                    scraper.scrape_news_rss(query, timeframe_days, search_config)
                )
                scraped_articles_data.extend(articles)
                if i < len(keywords) - 1:
                    loop.run_until_complete(asyncio.sleep(1.5))
        finally:
            loop.run_until_complete(scraper.close())
            loop.close()

        print(f"Scraper returned {len(scraped_articles_data)} raw items from Google News.")

        deduplicator = Deduplicator(time_window_days=14)
        articles_saved = 0
        relevant_count = 0

        for idx, art_data in enumerate(scraped_articles_data):
            run.status = f'Deduplicating & judging article ({idx+1}/{len(scraped_articles_data)}): "{art_data["title"][:40]}..."'
            run.save()
            
            # Process semantic deduplication and LLM relevance judgements
            processed = deduplicator.process_article(art_data, pulse)
            
            # Fetch matched original instance if Layer 1/2/3 duplicate matches exist
            matched_original_instance = None
            if processed.get('matched_original_id'):
                try:
                    matched_original_instance = Article.objects.get(id=processed['matched_original_id'])
                except Article.DoesNotExist:
                    pass

            article_obj = Article.objects.create(
                pulse=pulse,
                discovery_run=run,
                title=processed['title'],
                source=processed['source'],
                url=processed['url'],
                publication_date=processed.get('publication_date'),
                description=processed.get('description'),
                embedding=processed.get('embedding'),
                is_duplicate=processed.get('is_duplicate', False),
                matched_original=matched_original_instance,
                duplicate_reason=processed.get('duplicate_reason'),
                delta_summary=processed.get('delta_summary'),
                is_relevant=processed.get('is_relevant', False),
                relevance_score=processed.get('relevance_score', 0),
                buying_signal=processed.get('buying_signal'),
                relevance_tier=processed.get('relevance_tier', 'noise'),
                relevance_reason=processed.get('relevance_reason'),
                prompt_tokens=processed.get('prompt_tokens', 0),
                completion_tokens=processed.get('completion_tokens', 0),
                total_tokens=processed.get('total_tokens', 0)
            )
            
            articles_saved += 1
            if article_obj.is_relevant and not article_obj.is_duplicate:
                relevant_count += 1

        # Run summarizer and target entity extractions
        run.status = 'Summarizing high intent news and extracting target leads...'
        run.save()
        summarize_pulse_articles(pulse, run)
        
        # Calculate leads count
        leads_count = Lead.objects.filter(discovery_run=run).count()

        # Finalize run status logs
        run.status = 'completed'
        run.completed_at = timezone.now()
        run.articles_scraped = articles_saved
        run.articles_relevant = relevant_count
        run.leads_extracted = leads_count
        run.save()

        pulse.last_processed_at = timezone.now()
        pulse.save()
        
        print(f"Pipeline execution finished. Saved {articles_saved} articles ({relevant_count} relevant) and extracted {leads_count} leads.")
        
    except Exception as e:
        print(f"Pipeline execution encountered error: {e}")
        run.status = 'failed'
        run.completed_at = timezone.now()
        run.error_message = str(e)
        run.save()
        raise e
