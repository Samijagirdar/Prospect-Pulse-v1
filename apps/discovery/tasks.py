import asyncio
from datetime import datetime, timedelta
from django.utils import timezone
from celery import shared_task
from apps.pulses.models import Pulse
from .models import DiscoveryRun, Article, Lead, Notification
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
    
    # Create notification for run starting
    now_str = timezone.now().strftime('%d/%m/%Y')
    time_str = timezone.now().strftime('%H:%M')
    Notification.objects.create(
        title=f"Discovery Started for {pulse.name}",
        message=f"🚀 Discovery started for '{pulse.name}' on {now_str} at {time_str}. Scraping sources and analyzing target accounts..."
    )
    
    try:
        # Timeframe calculation (60 days back on first run, dynamic elapsed days on subsequent runs)
        run.status = 'calculating query timeframe...'
        run.save()
        completed_runs = DiscoveryRun.objects.filter(pulse=pulse, status='completed')
        if not completed_runs.exists() or not pulse.last_processed_at:
            timeframe_days = 60
            print(f"First run for pulse '{pulse.name}'. Using historical time window of 60 days.")
        else:
            import math
            delta = timezone.now() - pulse.last_processed_at
            elapsed_hours = delta.total_seconds() / 3600
            timeframe_days = math.ceil(elapsed_hours / 24)
            
            # Safe minimum & maximum bounds
            if timeframe_days < 1:
                timeframe_days = 1
            elif timeframe_days > 60:
                timeframe_days = 60
                
            print(f"Incremental run for pulse '{pulse.name}'. Last run was {elapsed_hours:.2f} hours ago. Using dynamic query window of {timeframe_days} days.")

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

        # Deduplicate scraped raw articles by URL first to avoid duplicate processing in the same run
        seen_urls = set()
        unique_scraped_articles = []
        for art in scraped_articles_data:
            url = art.get('url')
            if url not in seen_urls:
                seen_urls.add(url)
                unique_scraped_articles.append(art)
        scraped_articles_data = unique_scraped_articles
        
        print(f"Deduplicated to {len(scraped_articles_data)} unique raw items by URL.")

        deduplicator = Deduplicator(time_window_days=14)
        articles_saved = 0
        relevant_count = 0

        total_classification_calls = 0
        total_classification_prompt = 0
        total_classification_completion = 0
        total_classification_tokens = 0

        for idx, art_data in enumerate(scraped_articles_data):
            run.status = f'Deduplicating & judging article ({idx+1}/{len(scraped_articles_data)}): "{art_data["title"][:40]}..."'
            run.save()
            
            # Process semantic deduplication and LLM relevance judgements
            processed = deduplicator.process_article(art_data, pulse)
            
            # Track Relevance Judge token usage if an API call was made
            if not processed.get('is_duplicate', False):
                p_tok = processed.get('prompt_tokens', 0) or 0
                c_tok = processed.get('completion_tokens', 0) or 0
                t_tok = processed.get('total_tokens', 0) or 0
                if t_tok > 0:
                    total_classification_calls += 1
                    total_classification_prompt += p_tok
                    total_classification_completion += c_tok
                    total_classification_tokens += t_tok
            
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
            
            # Register newly saved article with Deduplicator in-memory cache
            deduplicator.register_processed_article(article_obj)
            
            articles_saved += 1
            if article_obj.is_relevant and not article_obj.is_duplicate:
                relevant_count += 1

        # Run summarizer and target entity extractions
        run.status = 'Summarizing high intent news and extracting target leads...'
        run.save()
        sum_prompt, sum_comp, sum_tot, sum_calls = summarize_pulse_articles(pulse, run)
        
        # Calculate leads count
        leads_count = Lead.objects.filter(discovery_run=run).count()

        # Finalize run status logs
        run.status = 'completed'
        run.completed_at = timezone.now()
        run.articles_scraped = articles_saved
        run.articles_relevant = relevant_count
        run.leads_extracted = leads_count
        run.save()

        # Compute overall stats and print total usage block
        total_calls = total_classification_calls + sum_calls
        total_prompt = total_classification_prompt + sum_prompt
        total_completion = total_classification_completion + sum_comp
        total_all_tokens = total_classification_tokens + sum_tot
        
        # Estimate cost (input $1.50/M tokens, output $9.00/M tokens)
        estimated_cost = (total_prompt * 0.00000150) + (total_completion * 0.00000900)
        
        print("\n" + "=" * 76, flush=True)
        print(f"             GEMINI API RUN SUMMARY: Discovery Run #{run.id}", flush=True)
        print(f"             Campaign: \"{pulse.name}\" (ID: {pulse.id})", flush=True)
        print("=" * 76, flush=True)
        print(f" • Total Gemini API Calls: {total_calls} (Classifications: {total_classification_calls}, Summaries: {sum_calls})", flush=True)
        print(f" • Total Input (Prompt) Tokens: {total_prompt:,}", flush=True)
        print(f" • Total Output (Completion) Tokens: {total_completion:,}", flush=True)
        print(f" • Total Tokens Consumed: {total_all_tokens:,}", flush=True)
        print(f" • Estimated Run Cost: ${estimated_cost:.5f} USD", flush=True)
        print("=" * 76 + "\n", flush=True)

        pulse.last_processed_at = timezone.now()
        pulse.save()
        
        # Create completion notification
        now_str = timezone.now().strftime('%d/%m/%Y')
        time_str = timezone.now().strftime('%H:%M')
        Notification.objects.create(
            title=f"Discovery Completed for {pulse.name}",
            message=f"✅ Discovery on {now_str} at {time_str} is completed for '{pulse.name}'. New sources and leads are discovered."
        )
        
        print(f"Pipeline execution finished. Saved {articles_saved} articles ({relevant_count} relevant) and extracted {leads_count} leads.")
        
    except Exception as e:
        print(f"Pipeline execution encountered error: {e}")
        run.status = 'failed'
        run.completed_at = timezone.now()
        run.error_message = str(e)
        run.save()
        
        # Create failure notification
        now_str = timezone.now().strftime('%d/%m/%Y')
        time_str = timezone.now().strftime('%H:%M')
        Notification.objects.create(
            title=f"Discovery Failed for {pulse.name}",
            message=f"⚠️ Discovery for '{pulse.name}' on {now_str} at {time_str} failed. Reason: {str(e)}"
        )
        raise e


@shared_task
def run_pulse_discovery_task(pulse_id, run_id=None):
    """
    Celery task wrapper for executing a discovery scan.
    """
    run_pulse_discovery(pulse_id, run_id)


@shared_task
def check_and_trigger_scheduled_pulses():
    """
    Celery Beat task running periodically to discover active campaign runs.
    Checks frequency schedule settings and deactivates campaigns whose end_date has passed.
    """
    now = timezone.now()
    # Filter only active campaigns that have run at least once (last_processed_at is not None)
    # as per customer instruction: campaigns only trigger automatically once manually started.
    active_pulses = Pulse.objects.filter(is_active=True, last_processed_at__isnull=False)
    
    print(f"Celery Beat check: Analyzing {active_pulses.count()} active scheduled campaigns at {now}...")
    
    for pulse in active_pulses:
        # 1. Deactivate if end_date has passed
        if pulse.end_date and now.date() > pulse.end_date:
            print(f"Celery Beat: Deactivating pulse '{pulse.name}' because current date is past end date ({pulse.end_date}).")
            pulse.is_active = False
            pulse.save()
            continue
            
        # 2. Skip if start_date has not arrived yet
        if pulse.start_date and now.date() < pulse.start_date:
            print(f"Celery Beat: Skipping pulse '{pulse.name}' - start date ({pulse.start_date}) is in the future.")
            continue
            
        # 3. Check elapsed time against campaign frequency configuration
        is_due = False
        reason = ""
        elapsed = now - pulse.last_processed_at
        elapsed_seconds = elapsed.total_seconds()
        
        # Define elapsed bounds based on campaign frequency
        if pulse.frequency == 'daily':
            # 24 hours (with a 5-minute grace window for periodic schedule drift)
            is_due = elapsed_seconds >= (24 * 3600 - 300)
            reason = f"Daily interval reached (elapsed: {elapsed_seconds/3600:.2f} hours)"
        elif pulse.frequency == 'weekly':
            # 7 days (with grace window)
            is_due = elapsed_seconds >= (7 * 24 * 3600 - 300)
            reason = f"Weekly interval reached (elapsed: {elapsed.days} days)"
        elif pulse.frequency == 'monthly':
            # 30 days (with grace window)
            is_due = elapsed_seconds >= (30 * 24 * 3600 - 300)
            reason = f"Monthly interval reached (elapsed: {elapsed.days} days)"
        elif pulse.frequency == 'custom' and pulse.custom_days:
            # Custom X days (with grace window)
            is_due = elapsed_seconds >= (pulse.custom_days * 24 * 3600 - 300)
            reason = f"Custom interval of {pulse.custom_days} days reached (elapsed: {elapsed.days} days)"
            
        if is_due:
            print(f"Celery Beat: Campaign '{pulse.name}' is due for execution. Reason: {reason}. Triggering task...")
            # Create the DiscoveryRun record with 'queued' state
            DiscoveryRun = pulse.discovery_runs.model
            run = DiscoveryRun.objects.create(
                pulse=pulse,
                status='queued',
                started_at=now
            )
            # Dispatch task asynchronously to the celery queue
            run_pulse_discovery_task.delay(pulse.id, run.id)

