import asyncio
from django.utils import timezone
from celery import shared_task
from apps.pulses.models import Pulse
from .models import DiscoveryRun, Article, Lead, Notification
from .pipeline.multi_source_scraper import MultiSourceScraper
from .pipeline.deduplicator import Deduplicator
from .pipeline.summarizer import summarize_pulse_articles
from .pipeline.lead_extractor import extract_pulse_leads

def run_pulse_discovery(pulse_id, run_id=None, timeframe_days_override=None):
    """
    Synchronous pipeline runner for executing a prospect pulse discovery scan.
    Calculates timeframe windows, scrapes articles, deduplicates, runs LLM judges,
    and extracts leads, target companies, and competitors.
    """
    pulse = Pulse.objects.get(id=pulse_id)
    
    # Check if pulse has reached its end date
    if pulse.is_expired:
        end_date_str = pulse.end_date.strftime('%d/%m/%Y') if pulse.end_date else ''
        err_msg = f"This pulse has reached its end date ({end_date_str}). Please edit your pulse and extend the end date to run discovery."
        print(f"Aborting discovery for pulse '{pulse.name}': {err_msg}")
        if run_id:
            try:
                run = DiscoveryRun.objects.get(id=run_id)
                run.status = 'failed'
                run.error_message = err_msg
                run.completed_at = timezone.now()
                run.save()
            except Exception:
                pass
        return

    # Initialize or fetch run log
    if run_id:
        run = DiscoveryRun.objects.get(id=run_id)
        if run.status == 'stopped':
            print(f"Run #{run.id} was already marked stopped before execution began.")
            return
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
        # Timeframe calculation with intelligent gap-filling
        run.status = 'calculating query timeframe...'
        run.save()
        lookback_map = {
            '30d': 30,
            '60d': 60,
            '90d': 90,
            '180d': 180,
            '365d': 365
        }
        max_configured_timeframe = lookback_map.get(getattr(pulse, 'historical_lookback', '60d'), 60)

        # 1. If an explicit timeframe override is provided, use it
        if timeframe_days_override and isinstance(timeframe_days_override, int) and timeframe_days_override > 0:
            timeframe_days = min(timeframe_days_override, max_configured_timeframe)
            print(f"Using explicit timeframe override of {timeframe_days} days for pulse '{pulse.name}'.")
        else:
            # 2. Intelligent Gap-Filling: Find the last run that ACTUALLY ingested articles
            last_successful_run = DiscoveryRun.objects.filter(
                pulse=pulse,
                status='completed',
                articles_scraped__gt=0
            ).exclude(id=run.id).order_by('-completed_at').first()

            if not last_successful_run or not last_successful_run.completed_at:
                timeframe_days = max_configured_timeframe
                print(f"First run (or no prior successful extractions) for pulse '{pulse.name}'. Using configured historical time window of {timeframe_days} days.")
            else:
                import math
                delta = timezone.now() - last_successful_run.completed_at
                elapsed_hours = delta.total_seconds() / 3600
                # Add a 1-day safety buffer so boundary articles right on the threshold are never missed
                timeframe_days = math.ceil(elapsed_hours / 24) + 1
                
                # Minimum 2-day lookback to account for RSS syndication delays and timezone differences
                if timeframe_days < 2:
                    timeframe_days = 2
                elif timeframe_days > max_configured_timeframe:
                    timeframe_days = max_configured_timeframe
                    
                print(f"Incremental run for pulse '{pulse.name}'. Last successful extraction was {elapsed_hours:.2f} hours ago (Run #{last_successful_run.id}). Using dynamic query window of {timeframe_days} days.")

        # Collect keywords and monitored competitors
        keywords = [kw.keyword for kw in pulse.keywords_rel.all()]
        if not keywords:
            keywords = ["Revenue Intelligence Platform", "Sales Automation Software", "AI Lead Generation"]
            print("No keywords configured. Using default placeholder search terms.")

        # Actively monitor configured and discovered competitors in the scraping query pool
        competitors = [c.competitor_name.strip() for c in pulse.competitors.all() if c.competitor_name.strip()]
        search_terms = list(keywords)
        for comp in competitors[:8]:  # actively scrape top monitored competitors
            if comp and comp not in search_terms:
                search_terms.append(comp)

        print(f"Scraper search query pool: {len(search_terms)} queries ({len(keywords)} keywords + {len(search_terms) - len(keywords)} monitored competitors).")

        # Initialize multi-source scraper
        scraper = MultiSourceScraper()
        
        # Fetch existing URLs already discovered for this pulse to skip re-scraping them
        existing_urls = set(Article.objects.filter(pulse=pulse).values_list('url', flat=True))

        # Execute scraping query loops across all sources in parallel
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        scraped_articles_data = []
        try:
            run.status = f'Ingesting signals in parallel across Google News, Tech Funding, PR Wires & Hacker News...'
            run.save()
            scraped_articles_data = loop.run_until_complete(
                scraper.scrape_all_sources_parallel(search_terms, timeframe_days, existing_urls=existing_urls)
            )
        finally:
            loop.close()

        print(f"Multi-source scraper returned {len(scraped_articles_data)} new raw items.")

        # Deduplicate scraped raw articles by URL first to avoid duplicate processing in the same run
        seen_urls = set(existing_urls)
        unique_scraped_articles = []
        for art in scraped_articles_data:
            url = art.get('url')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_scraped_articles.append(art)
        scraped_articles_data = unique_scraped_articles
        
        print(f"Deduplicated to {len(scraped_articles_data)} unique new raw items by URL.")

        deduplicator = Deduplicator(time_window_days=14)
        articles_saved = 0
        relevant_count = 0

        total_classification_calls = 0
        total_classification_prompt = 0
        total_classification_completion = 0
        total_classification_tokens = 0

        def _finalize_stopped_run(c_prompt=0, c_comp=0, c_tot=0):
            leads_cnt = Lead.objects.filter(discovery_run=run).count()
            run.completed_at = timezone.now()
            run.articles_scraped = articles_saved
            run.articles_relevant = relevant_count
            run.leads_extracted = leads_cnt
            run.prompt_tokens = c_prompt
            run.completion_tokens = c_comp
            run.total_tokens = c_tot
            run.status = 'stopped'
            run.save()

            pulse.last_processed_at = timezone.now()
            pulse.save()

            now_str = timezone.now().strftime('%d/%m/%Y')
            time_str = timezone.now().strftime('%H:%M')
            Notification.objects.create(
                title=f"Discovery Stopped for {pulse.name}",
                message=f"🛑 Discovery run #{run.id} for '{pulse.name}' stopped on {now_str} at {time_str}. Preserved {articles_saved} articles ({relevant_count} relevant) and {leads_cnt} leads."
            )
            print(f"Discovery run #{run.id} finalized cleanly in 'stopped' state.")

        # Check if run was stopped immediately after scraping
        run.refresh_from_db(fields=['status'])
        if run.status == 'stopped':
            _finalize_stopped_run(0, 0, 0)
            return

        stopped_early = False
        for idx, art_data in enumerate(scraped_articles_data):
            run.refresh_from_db(fields=['status'])
            if run.status == 'stopped':
                stopped_early = True
                print(f"Run #{run.id} was stopped by user during deduplication/judging (item {idx+1}/{len(scraped_articles_data)}).")
                break

            run.status = f'Deduplicating & judging article ({idx+1}/{len(scraped_articles_data)}): "{art_data["title"][:40]}..."'
            run.save()
            
            # Process semantic deduplication and LLM relevance judgements
            processed = deduplicator.process_article(art_data, pulse)
            
            # If it turned out to be an exact URL match against database, drop it silently
            if processed.get('duplicate_reason') == "Layer 1: URL Hash Match":
                continue

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
            
            # Fetch matched original instance if Layer 2/2.5/3 duplicate matches exist
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

        if stopped_early:
            _finalize_stopped_run(total_classification_prompt, total_classification_completion, total_classification_tokens)
            return

        run.refresh_from_db(fields=['status'])
        if run.status == 'stopped':
            _finalize_stopped_run(total_classification_prompt, total_classification_completion, total_classification_tokens)
            return

        # Stage 3: Fast Executive Article Summarization (Gemini 3.8 Flash)
        run.status = 'Summarizing relevant news articles with Gemini 3.8 Flash...'
        run.save()
        sum_prompt, sum_comp, sum_tot, sum_calls = summarize_pulse_articles(pulse, run)

        run.refresh_from_db(fields=['status'])
        if run.status == 'stopped':
            _finalize_stopped_run(
                total_classification_prompt + sum_prompt,
                total_classification_completion + sum_comp,
                total_classification_tokens + sum_tot
            )
            return

        # Stage 4: Decision-Maker Leads Extraction (Disburse.dev with toggleable Gemini fallback)
        import os
        from .pipeline.disburse_lead_extractor import extract_pulse_leads_disburse

        enable_gemini_leads = os.getenv("ENABLE_GEMINI_LEAD_EXTRACTION", "false").lower() == "true"
        lead_prompt, lead_comp, lead_tot, lead_calls = 0, 0, 0, 0

        run.status = 'Discovering decision-maker leads & contact details via Disburse.dev...'
        run.save()
        extract_pulse_leads_disburse(pulse, run)

        if enable_gemini_leads:
            run.status = 'Augmenting leads via Gemini 3.8 Flash search grounding...'
            run.save()
            lead_prompt, lead_comp, lead_tot, lead_calls = extract_pulse_leads(pulse, run)
        else:
            print("[Stage 4] Gemini search grounding lead extraction is PAUSED (saving tokens).")

        run.refresh_from_db(fields=['status'])
        if run.status == 'stopped':
            _finalize_stopped_run(
                total_classification_prompt + sum_prompt + lead_prompt,
                total_classification_completion + sum_comp + lead_comp,
                total_classification_tokens + sum_tot + lead_tot
            )
            return
        
        # Calculate leads count
        leads_count = Lead.objects.filter(discovery_run=run).count()

        # Compute overall stats and print total usage block
        total_calls = total_classification_calls + sum_calls + lead_calls
        total_prompt = total_classification_prompt + sum_prompt + lead_prompt
        total_completion = total_classification_completion + sum_comp + lead_comp
        total_all_tokens = total_classification_tokens + sum_tot + lead_tot

        # Finalize run status logs
        run.status = 'completed'
        run.completed_at = timezone.now()
        run.articles_scraped = articles_saved
        run.articles_relevant = relevant_count
        run.leads_extracted = leads_count
        run.prompt_tokens = total_prompt
        run.completion_tokens = total_completion
        run.total_tokens = total_all_tokens
        run.save()
        
        # Estimate cost (input $0.075/M tokens, output $0.30/M tokens)
        estimated_cost = (total_prompt * 0.000000075) + (total_completion * 0.00000030)
        
        print("\n" + "=" * 76, flush=True)
        print(f"             GEMINI API RUN SUMMARY: Discovery Run #{run.id}", flush=True)
        print(f"             Campaign: \"{pulse.name}\" (ID: {pulse.id})", flush=True)
        print("=" * 76, flush=True)
        print(f" • Total Gemini API Calls: {total_calls} (Classifications: {total_classification_calls}, Summaries: {sum_calls}, Lead Extractions: {lead_calls})", flush=True)
        print(f" • Total Input (Prompt) Tokens: {total_prompt:,}", flush=True)
        print(f" • Total Output (Completion) Tokens: {total_completion:,}", flush=True)
        print(f" • Total Tokens Consumed: {total_all_tokens:,}", flush=True)
        print(f" • Estimated Run Cost: ${estimated_cost:.5f} USD", flush=True)
        print("=" * 76 + "\n", flush=True)

        # Only advance pulse.last_processed_at if articles were actually discovered and saved
        # This prevents 0-article failed/empty runs from causing a permanent time blind spot
        if articles_saved > 0:
            pulse.last_processed_at = timezone.now()
            pulse.save(update_fields=['last_processed_at'])
            print(f"Updated pulse.last_processed_at to {pulse.last_processed_at} ({articles_saved} articles saved).")
        else:
            print(f"Pulse '{pulse.name}' saved 0 articles. Preserving previous last_processed_at ({pulse.last_processed_at}) to allow subsequent gap-filling.")
        
        # Create completion notification
        now_str = timezone.now().strftime('%d/%m/%Y')
        time_str = timezone.now().strftime('%H:%M')
        Notification.objects.create(
            title=f"Discovery Completed for {pulse.name}",
            message=f"✅ Discovery on {now_str} at {time_str} is completed for '{pulse.name}'. New sources and leads are discovered."
        )
        
        print(f"Pipeline execution finished. Saved {articles_saved} articles ({relevant_count} relevant) and extracted {leads_count} leads.")
        
    except Exception as e:
        # Check if the run was stopped by the user - do not overwrite 'stopped' with 'failed'
        try:
            run.refresh_from_db(fields=['status'])
            if run.status == 'stopped':
                print(f"Pipeline caught exception while in stopped state; suppressing error: {e}")
                return
        except Exception:
            pass

        print(f"Pipeline execution encountered error: {e}")
        err_str = str(e)
        if any(keyword in err_str for keyword in ["PERMISSION_DENIED", "CONSUMER_SUSPENDED", "403", "UNAUTHENTICATED", "401", "api_key"]):
            clean_err = "API Error please contact your administrator"
        elif any(keyword in err_str for keyword in ["RESOURCE_EXHAUSTED", "quota", "spending cap", "429"]):
            clean_err = "API Quota Exceeded. Please check your Google AI Studio spend caps."
        else:
            import re
            clean_err = re.sub(r'api_key[=:][A-Za-z0-9_\-]+', 'api_key=***HIDDEN***', err_str)

        run.status = 'failed'
        run.completed_at = timezone.now()
        run.error_message = clean_err
        run.save()
        
        # Create failure notification
        now_str = timezone.now().strftime('%d/%m/%Y')
        time_str = timezone.now().strftime('%H:%M')
        Notification.objects.create(
            title=f"Discovery Failed for {pulse.name}",
            message=f"⚠️ Discovery for '{pulse.name}' on {now_str} at {time_str} failed. Reason: {clean_err}"
        )
        raise e


@shared_task
def run_pulse_discovery_task(pulse_id, run_id=None, timeframe_days_override=None):
    """
    Celery task wrapper for executing a discovery scan.
    """
    run_pulse_discovery(pulse_id, run_id, timeframe_days_override)


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
            
        if is_due:
            # Check if there is already an active run for this pulse before queueing another
            has_active_run = pulse.discovery_runs.filter(
                status__in=['queued', 'starting', 'scraping', 'processing', 'in_progress']
            ).exclude(status__in=['completed', 'failed']).exists()

            if has_active_run:
                print(f"Celery Beat: Skipping trigger for pulse '{pulse.name}' - a discovery run is already active.")
                continue

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

