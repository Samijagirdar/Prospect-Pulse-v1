import os
import json
import re
from datetime import datetime
from django.utils import timezone

# Safe import of Google GenAI SDK
try:
    from google import genai as google_genai
    from google.genai import types as genai_types
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    google_genai = None
    genai_types = None
    GOOGLE_GENAI_AVAILABLE = False

from apps.discovery.models import Article, Company, Lead, Competitor

# Create the client ONCE
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


def normalize_company_name(name):
    if not name:
        return ""
    name = name.strip()
    # Pattern to match common legal suffixes at the end of the company name
    pattern = r'\b(plc|ltd|inc|corp|co|llc|gmbh|sa|limited|corporation|incorporated|pvt\s+ltd|s\.a\.?|l\.t\.d\.?|i\.n\.c\.?)\b\.?$'
    cleaned = re.sub(pattern, '', name, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'[\s,\.]+$', '', cleaned).strip()
    return cleaned if cleaned else name


def is_invalid_name(name):
    if not name:
        return True
    name_lower = name.strip().lower()
    invalid_titles = [
        'chief information officer', 'cio', 
        'chief information security officer', 'ciso',
        'chief technology officer', 'cto',
        'managing director', 'ceo', 'president',
        'chief executive officer', 'vp', 'vice president',
        'head of operations', 'operations manager',
        'director', 'manager', 'executive', 'representative',
        'partner', 'associate', 'consultant', 'analyst',
        'c-level', 'administrator', 'coordinator'
    ]
    if name_lower in invalid_titles:
        return True
    if len(name.strip()) < 3 or len(name.strip()) > 50:
        return True
    return False


def extract_json_by_matching_braces(text):
    first_brace = text.find('{')
    if first_brace == -1:
        return text
        
    brace_count = 0
    in_string = False
    escape = False
    
    for i in range(first_brace, len(text)):
        char = text[i]
        
        if escape:
            escape = False
            continue
            
        if char == '\\':
            escape = True
            continue
            
        if char == '"':
            in_string = not in_string
            continue
            
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[first_brace:i+1]
                    
    return text[first_brace:]

def repair_truncated_json(text):
    """
    Robustly repairs truncated or malformed JSON strings from LLMs.
    Closes open quotes, strips trailing commas/incomplete keys, and closes open braces/brackets.
    """
    if not text:
        return "{}"
        
    cleaned = text.strip()
    
    # Find first '{'
    first_brace = cleaned.find('{')
    if first_brace == -1:
        return "{}"
    
    candidate = cleaned[first_brace:]
    
    # State tracking
    stack = []
    in_string = False
    escape = False
    i = 0
    limit = len(candidate)
    
    while i < limit:
        char = candidate[i]
        
        if escape:
            escape = False
            i += 1
            continue
            
        if char == '\\':
            escape = True
            i += 1
            continue
            
        if char == '"':
            in_string = not in_string
            i += 1
            continue
            
        if not in_string:
            if char == '{':
                stack.append('{')
            elif char == '[':
                stack.append('[')
            elif char == '}':
                if stack and stack[-1] == '{':
                    stack.pop()
            elif char == ']':
                if stack and stack[-1] == '[':
                    stack.pop()
        i += 1

    # If we ended inside a string, close the quote
    repaired = candidate
    if in_string:
        repaired += '"'
        in_string = False
        
    # Strip any trailing whitespace
    repaired = repaired.strip()
    
    # Loop to strip trailing invalid elements (commas, keys with colons but no values, etc.)
    while True:
        original = repaired
        repaired = re.sub(r',\s*$', '', repaired)
        repaired = re.sub(r'"[^"]*"\s*:\s*$', '', repaired)
        repaired = re.sub(r',\s*$', '', repaired)
        repaired = re.sub(r',\s*"[^"]*"\s*$', '', repaired)
        if repaired == original:
            break
            
    # Rebuild stack to close open brackets/braces accurately
    final_stack = []
    in_str = False
    esc = False
    for c in repaired:
        if esc:
            esc = False
            continue
        if c == '\\':
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if not in_str:
            if c == '{':
                final_stack.append('{')
            elif c == '[':
                final_stack.append('[')
            elif c == '}':
                if final_stack and final_stack[-1] == '{':
                    final_stack.pop()
            elif c == ']':
                if final_stack and final_stack[-1] == '[':
                    final_stack.pop()
                    
    # Close any open structures in reverse order
    for sym in reversed(final_stack):
        if sym == '{':
            repaired += '}'
        elif sym == '[':
            repaired += ']'
            
    return repaired

def clean_and_parse_json(text):
    if not text:
        raise ValueError("Empty response text from LLM")

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    # 1. Try standard brace matching extraction
    json_candidate = extract_json_by_matching_braces(cleaned)
    try:
        return json.loads(json_candidate)
    except json.JSONDecodeError:
        pass

    # 2. Try trailing comma cleanup
    json_candidate_fixed = re.sub(r',\s*([\}\]])', r'\1', json_candidate)
    try:
        return json.loads(json_candidate_fixed)
    except json.JSONDecodeError:
        pass

    # 3. Try full structural repair (truncation/missing brackets)
    try:
        repaired = repair_truncated_json(cleaned)
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Basic regex backup if JSON format is slightly broken
    summary_match = re.search(r'"summary"\s*:\s*"([^"]+)"', json_candidate, re.IGNORECASE)
    if summary_match:
        return {
            "summary": summary_match.group(1),
            "companies": [],
            "competitors": [],
            "leads": []
        }

    raise ValueError(f"Unable to parse valid JSON from LLM: {text[:200]}")


def summarize_pulse_articles(pulse, discovery_run=None, articles_qs=None):
    """
    Query unsummarized relevant articles for this pulse and extract leads/companies/competitors using Gemini.
    """
    client = _get_client()
    if articles_qs is not None:
        articles = articles_qs
    else:
        articles = Article.objects.filter(pulse=pulse, is_relevant=True, is_duplicate=False, is_summarized=False)

    if not articles.exists():
        print(f"No new relevant articles to summarize for pulse: {pulse.name}")
        return 0, 0, 0, 0

    print(f"Found {articles.count()} relevant articles to summarize for pulse: {pulse.name}")

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    num_calls = 0

    for art in articles:
        title = art.title
        desc = art.description or ""
        art_id = art.id
        buying_signal = art.buying_signal or "General B2B Intent"

        competitor_names_list = ", ".join(pulse.competitors_list) or "None configured"

        prompt = f"""
You are an expert sales intelligence assistant with access to Google Search grounding. Read the B2B news article below and perform 4 tasks.

**KNOWN COMPETITORS FOR THIS CAMPAIGN** (check against these first):
{competitor_names_list}

**ARTICLE**:
- Title: {title}
- Description: {desc}
- Context/Signal: {buying_signal}

**TASKS**:
1. Write a 120-word executive summary focused on target account business growth, digital initiatives, and potential needs.
2. Extract EVERY company mentioned in the article that shows B2B buyer intent (not just the primary subject) — score each 0-100 and map to a buying signal.
3. For each company extracted, classify as a competitor ONLY if:
   a) it fuzzy-matches a name in the KNOWN COMPETITORS list above (set "matched_known_competitor": true), OR
   b) it clearly offers competing services same as ours (such as B2B lead generation, web scraping, AI-driven relevance classification, CRM data enrichment, sales intelligence, and prospecting services) and is not on the known list (set "matched_known_competitor": false).
   Competitors MUST NOT also appear in the 'companies' array — list them ONLY in 'competitors'.
4. For all extracted target companies showing B2B buyer intent, use Google Search to find their key decision-makers and technical influencers involved in SaaS/sales tech evaluation (such as CEO, CIO, CTO, VP Operations, VP Sales, VP Marketing, Head of Engineering, Technical Lead, Solutions Architect, Software Engineer, IT Manager, etc.) and extract only their names and designations. Do not search the web for their emails or phone numbers; if these contact details are not explicitly present in the article text, set them as null.

**RULES**:
- Set score higher (80-100) for hot buyer intent, lower (40-70) for thought leadership or general news.
- Ensure that designations represent standard job titles (e.g. CIO, VP Sales).
- Do not list competitors in the 'companies' or 'leads_mentioned' arrays.

Return your answer as a JSON object matching this structure EXACTLY:
{{
  "summary": "120-word executive summary",
  "companies": [
     {{
       "name": "Company Name",
       "score": 0-100,
       "buying_signal": "intent signal name",
       "reason": "explanation of classification"
     }}
  ],
  "competitors": [
     {{
       "name": "Competitor Company Name",
       "matched_known_competitor": true,
       "buying_signal": "competing signal",
       "reason": "explanation of why classified as competitor"
     }}
  ],
  "leads_mentioned": [
     {{
       "name": "Full Name",
       "designation": "Job Title",
       "organization_name": "Company Name",
       "score": 0-100,
       "buying_signal": "intent signal",
       "reason": "why they are a hot lead",
       "email": "email address if found, else null",
       "phone": "phone number if found, else null"
     }}
  ]
}}
"""

        try:
            model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        tools=[{"google_search": {}}],
                        max_output_tokens=4096
                    )
                )
                if not response.text:
                    raise ValueError("Empty response text from LLM")
            except Exception as first_err:
                print(f"Summarizer: First attempt with search grounding failed or returned empty: {first_err}. Retrying without search grounding...")
                
                # Define fallback prompt without Google Search grounding instructions
                fallback_prompt = prompt.replace("with access to Google Search grounding", "analyzing B2B news")
                fallback_prompt = fallback_prompt.replace(
                    "use Google Search to find their key decision-makers and technical influencers involved in SaaS/sales tech evaluation (such as CEO, CIO, CTO, VP Operations, VP Sales, VP Marketing, Head of Engineering, Technical Lead, Solutions Architect, Software Engineer, IT Manager, etc.) and extract only their names and designations. Do not search the web for their emails or phone numbers;",
                    "extract key decision-makers and technical influencers (such as CEO, CIO, CTO, VP Operations, VP Sales, VP Marketing, Head of Engineering, Technical Lead, Solutions Architect, Software Engineer, IT Manager, etc.) explicitly from the article text or your knowledge base. Do not search the web;"
                )
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=fallback_prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=4096
                    )
                )
                if not response.text:
                    raise ValueError("Empty response text from LLM on retry without search grounding")

            # Extract and print individual summarizer token usage
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

            print(f"[Gemini API] Call: Summarizer | Prompt: {prompt_tokens} | Completion: {completion_tokens} | Total: {tot_tokens} tokens", flush=True)

            res_json = clean_and_parse_json(response.text)

            summary = res_json.get("summary", "No summary generated.")
            companies = res_json.get("companies", [])
            competitors = res_json.get("competitors", [])
            leads = res_json.get("leads_mentioned", []) or res_json.get("leads", [])

            # Update article summary details
            art.executive_summary = summary
            art.is_summarized = True
            art.save()

            # Enforce mutual exclusivity
            competitor_names = {normalize_company_name(c.get('name') or '').strip().lower() for c in competitors if c.get('name')}
            
            # Fetch existing competitors for this pulse
            db_competitors = {comp.name.strip().lower() for comp in Competitor.objects.filter(pulse=pulse)}
            all_competitors = competitor_names | db_competitors

            # Insert Competitors first
            for comp in competitors:
                raw_name = comp.get('name')
                if not raw_name:
                    continue
                comp_name = normalize_company_name(str(raw_name).strip())
                if not comp_name:
                    continue
                try:
                    Competitor.objects.update_or_create(
                        pulse=pulse,
                        name=comp_name,
                        defaults={
                            'buying_signal': comp.get('buying_signal', buying_signal),
                            'reason': comp.get('reason'),
                            'source_article': art,
                            'discovery_run': discovery_run
                        }
                    )
                    # Clean downstream tables to keep list mutually exclusive
                    Company.objects.filter(pulse=pulse, name__iexact=comp_name).delete()
                    Lead.objects.filter(pulse=pulse, organization_name__iexact=comp_name).delete()
                except Exception as ce:
                    print(f"Error saving competitor {comp_name}: {ce}")

            # Insert Companies (excluding competitors)
            for c in companies:
                raw_name = c.get('name')
                if not raw_name:
                    continue
                comp_name = normalize_company_name(str(raw_name).strip())
                if not comp_name:
                    continue
                if comp_name.lower() in all_competitors:
                    print(f"Excluding company '{comp_name}' from direct leads list because it is classified as a competitor.")
                    continue
                try:
                    Company.objects.update_or_create(
                        pulse=pulse,
                        name=comp_name,
                        defaults={
                            'score': c.get('score', 50),
                            'buying_signal': c.get('buying_signal', buying_signal),
                            'reason': c.get('reason'),
                            'source_article': art,
                            'discovery_run': discovery_run
                        }
                    )
                except Exception as ce:
                    print(f"Error saving company {comp_name}: {ce}")

            # Deduplicate leads at memory level and filter invalid names
            unique_leads = []
            seen_leads = set()
            for l in leads:
                lead_name = (l.get('name') or '').strip()
                org_name = normalize_company_name(l.get('organization_name') or '').strip()
                
                if not lead_name or not org_name:
                    continue
                if is_invalid_name(lead_name):
                    print(f"Excluding lead with invalid/placeholder name: '{lead_name}' at '{org_name}'")
                    continue
                
                key = (lead_name.lower(), org_name.lower())
                if key in seen_leads:
                    print(f"Excluding duplicate lead in response: '{lead_name}' at '{org_name}'")
                    continue
                seen_leads.add(key)
                unique_leads.append(l)

            # Insert Leads
            for l in unique_leads:
                lead_name = (l.get('name') or '').strip()
                org_name = normalize_company_name(l.get('organization_name') or '').strip()
                
                if not lead_name:
                    continue
                if org_name.lower() in all_competitors:
                    print(f"Excluding lead '{lead_name}' because organization '{org_name}' is classified as a competitor.")
                    continue
                    
                # Prevent duplicate leads for this pulse
                if Lead.objects.filter(pulse=pulse, name__iexact=lead_name, organization_name__iexact=org_name).exists():
                    print(f"Lead '{lead_name}' at '{org_name}' already exists in database. Skipping duplicate.")
                    continue
                    
                try:
                    Lead.objects.create(
                        pulse=pulse,
                        discovery_run=discovery_run,
                        source_article=art,
                        name=lead_name,
                        designation=l.get('designation'),
                        organization_name=org_name,
                        score=l.get('score', 50),
                        buying_signal=l.get('buying_signal', buying_signal),
                        reason=l.get('reason'),
                        email=l.get('email'),
                        phone=l.get('phone')
                    )
                except Exception as le:
                    print(f"Error saving lead {lead_name}: {le}")

            print(f"Processed article {art_id}: '{title[:50]}...' -> Summary & entities generated.")

        except Exception as e:
            print(f"Error processing article {art_id}: {e}")
            raise e

    print("Pulse summarization and lead extraction complete.")
    return total_prompt_tokens, total_completion_tokens, total_tokens, num_calls
