import os

# Safe import of Google GenAI SDK
try:
    from google import genai as google_genai
    from google.genai import types as genai_types
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    google_genai = None
    genai_types = None
    GOOGLE_GENAI_AVAILABLE = False

from apps.discovery.models import Article
from .lead_extractor import clean_and_parse_json

# Singleton client
_client = None

def _get_client():
    global _client
    if _client is not None:
        return _client
    if not GOOGLE_GENAI_AVAILABLE:
        raise ImportError("google-genai package is not installed.")
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Google API key is not configured. Add GOOGLE_API_KEY to your environment.")
    _client = google_genai.Client(api_key=api_key)
    return _client


def summarize_pulse_articles(pulse, discovery_run=None, articles_qs=None):
    """
    Dedicated article summarizer module using Gemini 3.8 Flash.
    Generates high-density B2B executive summaries for unsummarized relevant articles
    without external search grounding tool overhead.
    """
    client = _get_client()
    if articles_qs is not None:
        articles = articles_qs
    elif discovery_run:
        articles = Article.objects.filter(discovery_run=discovery_run, is_relevant=True, is_duplicate=False, is_summarized=False)
    else:
        articles = Article.objects.filter(pulse=pulse, is_relevant=True, is_duplicate=False, is_summarized=False)

    if not articles.exists():
        print(f"Summarizer: No new relevant articles to summarize for pulse: {pulse.name}")
        return 0, 0, 0, 0

    print(f"Summarizer: Summarizing {articles.count()} articles for pulse: {pulse.name}")

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    num_calls = 0

    primary_model = os.getenv("GEMINI_SUMMARIZER_MODEL", "gemini-3.8-flash")
    fallback_model = os.getenv("GEMINI_BACKUP_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.7-flash"))

    pulse_name = pulse.name or "B2B Sales Intelligence"
    profile = getattr(pulse, 'company_profile', None)
    target_account_focus = (getattr(profile, 'target_account_focus', None) or "").strip()
    target_industry = (getattr(profile, 'industry', None) or "").strip()
    product_service = target_account_focus or target_industry or pulse_name
    competitor_names_list = ", ".join(pulse.competitors_list) or "None currently configured"

    for art in articles:
        if discovery_run:
            discovery_run.refresh_from_db(fields=['status'])
            if discovery_run.status == 'stopped':
                print(f"Summarizer: DiscoveryRun #{discovery_run.id} was stopped by user. Exiting summarization loop.")
                break

        title = art.title or ""
        desc = art.description or ""
        art_id = art.id
        buying_signal = art.buying_signal or "General Intent"

        prompt = f"""You are an executive sales and market intelligence analyst. Analyze the following news article and generate a cohesive, high-density executive paragraph summary (maximum 120 words), and extract the primary commercial target company and competitor vendor companies.

CAMPAIGN TARGET:
- Campaign: {pulse_name}
- Product / Solution Domain: {product_service}
- Signal Classification: {buying_signal}
- Known Monitored Competitors: {competitor_names_list}

ARTICLE SOURCE DETAILS:
- Title: {title}
- Content Snippet: {desc}

CRITICAL RULES:
1. Summarize ONLY facts, announcements, and context directly mentioned in the article title and snippet.
2. Do NOT invent or extrapolate corporate details, expansions, or geographic regions.
3. Focus on the core business development, operational/commercial impact, and sales intelligence relevance for {pulse_name}.
4. Extract "target_company": The specific company name that is adopting, purchasing, expanding, hiring, deploying tech, or raising funds. If it is a generic industry report or no specific company is adopting, set to null.
5. Extract "competitor_companies": Array of vendor or solution provider companies mentioned in the snippet operating as competitors or alternatives in this market ({product_service}).
   For each competitor:
   - "name": Exact Company Name
   - "competitor_type": "direct" if directly offering competing products/services in {product_service} or matching known competitors; "indirect" if offering adjacent/alternative solutions.
   - "buying_signal": Specific strategic move (e.g., "Product Launch", "Market Expansion", "Strategic Partnership", "Leadership Hiring", "Fundraising / Capital", "Competing Solution", etc.)
   - "reason": Concise, articulate factual summary explaining their specific strategic move and competitive impact (e.g. "[Company] is expanding its [capabilities] to offer [features], directly competing with [domain] solution offerings"). CRITICAL: Do NOT include "[Direct Competitor]" or "[Indirect Alternative]" in the "reason" field itself; that classification is stored separately in "competitor_type".
6. Write a cohesive, professional paragraph strictly under 120 words for "summary". Do NOT format as bullet points.

Return your response as a JSON object matching this schema:
{{
  "summary": "Your cohesive executive paragraph summary here (under 120 words).",
  "target_company": "Exact Company Name or null",
  "competitor_companies": [
    {{
      "name": "Vendor Name",
      "competitor_type": "direct",
      "buying_signal": "Product Launch",
      "reason": "Clear explanation of what they are doing and how they compete"
    }}
  ]
}}
"""

        try:
            response = None
            try:
                response = client.models.generate_content(
                    model=primary_model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=1024
                    )
                )
                if not response or not response.text:
                    raise ValueError("Empty response text from LLM")
            except Exception as first_err:
                print(f"Summarizer: Primary model {primary_model} failed ({first_err}). Retrying with {fallback_model}...")
                response = client.models.generate_content(
                    model=fallback_model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=1024
                    )
                )
                if not response or not response.text:
                    raise ValueError("Empty response text on retry")

            # Extract token usage
            prompt_tokens = 0
            completion_tokens = 0
            tot_tokens = 0
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
                completion_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0
                tot_tokens = getattr(response.usage_metadata, 'total_token_count', 0) or (prompt_tokens + completion_tokens)
                total_prompt_tokens += prompt_tokens
                total_completion_tokens += completion_tokens
                total_tokens += tot_tokens
                num_calls += 1

            print(f"[Gemini 3.8 Summarizer] Article #{art_id} | In: {prompt_tokens} | Out: {completion_tokens} | Total: {tot_tokens} tokens", flush=True)

            res_json = clean_and_parse_json(response.text)
            summary_text = res_json.get("summary", "No summary generated.").strip()

            # Persist summary
            art.executive_summary = summary_text
            art.is_summarized = True
            art.save(update_fields=['executive_summary', 'is_summarized'])

            # Persist extracted target company if present
            target_company_name = (res_json.get("target_company") or "").strip()
            if target_company_name and target_company_name.lower() not in ["null", "none", "n/a"]:
                from apps.discovery.models import Company
                Company.objects.update_or_create(
                    pulse=pulse,
                    name=target_company_name,
                    defaults={
                        'score': art.relevance_score or 80,
                        'buying_signal': art.buying_signal or "Target Account Commercial Intent",
                        'reason': f"Extracted from intent signal: {art.title[:120]}",
                        'source_article': art,
                        'discovery_run': discovery_run
                    }
                )
                print(f"Summarizer: Registered target company '{target_company_name}' for pulse '{pulse.name}'.")

            # Persist competitor companies if present
            comp_items = res_json.get("competitor_companies") or []
            if isinstance(comp_items, list):
                from apps.discovery.models import Competitor
                from apps.pulses.models import TargetCompetitor
                import re

                for item in comp_items:
                    if isinstance(item, str):
                        c_clean = str(item).strip()
                        c_type = "direct"
                        c_sig = "Competing Solution"
                        c_reason = f"{c_clean} is actively expanding and offering competing solutions in the {product_service} market."
                    elif isinstance(item, dict):
                        c_clean = str(item.get("name") or "").strip()
                        c_type = str(item.get("competitor_type") or "direct").lower()
                        c_type = "indirect" if "indirect" in c_type else "direct"
                        c_sig = str(item.get("buying_signal") or "Competing Solution").strip()
                        raw_reason = str(item.get("reason") or "").strip()
                        c_reason = re.sub(r"^\[(Direct Competitor|Indirect Alternative)\]\s*", "", raw_reason, flags=re.IGNORECASE).strip()
                        if not c_reason:
                            c_reason = f"{c_clean} is actively expanding and offering competing capabilities in this domain."
                    else:
                        continue

                    if c_clean and c_clean.lower() not in ["null", "none", "n/a"]:
                        Competitor.objects.update_or_create(
                            pulse=pulse,
                            name=c_clean,
                            source_article=art,
                            defaults={
                                'competitor_type': c_type,
                                'buying_signal': c_sig,
                                'reason': c_reason,
                                'source_article': art,
                                'discovery_run': discovery_run
                            }
                        )
                        # Ensure registered in monitored competitors so future runs actively track it
                        if not TargetCompetitor.objects.filter(pulse=pulse, competitor_name__iexact=c_clean).exists():
                            TargetCompetitor.objects.create(
                                pulse=pulse,
                                competitor_name=c_clean
                            )

            print(f"Summarizer: Article #{art_id} saved successfully.")

        except Exception as e:
            print(f"Summarizer: Error summarizing article #{art_id}: {e}")
            # Do not crash the entire pipeline for one article
            continue

    print("Pulse article summarization stage complete.")
    return total_prompt_tokens, total_completion_tokens, total_tokens, num_calls
