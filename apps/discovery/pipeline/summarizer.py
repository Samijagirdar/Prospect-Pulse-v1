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


def clean_and_parse_json(text):
    if not text:
        raise ValueError("Empty response text from LLM")

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        json_candidate = match.group(0)
    else:
        json_candidate = cleaned

    try:
        return json.loads(json_candidate)
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


def summarize_pulse_articles(pulse, discovery_run=None):
    """
    Query unsummarized relevant articles for this pulse and extract leads/companies/competitors using Gemini.
    """
    client = _get_client()
    articles = Article.objects.filter(pulse=pulse, is_relevant=True, is_duplicate=False, is_summarized=False)

    if not articles.exists():
        print(f"No new relevant articles to summarize for pulse: {pulse.name}")
        return

    print(f"Found {articles.count()} relevant articles to summarize for pulse: {pulse.name}")

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
   b) it clearly offers competing sales intelligence, CRM, or SaaS services and is not on the known list (set "matched_known_competitor": false).
   Competitors MUST NOT also appear in the 'companies' array — list them ONLY in 'competitors'.
4. For all extracted target companies showing B2B buyer intent, use Google Search to find their key decision-makers (such as CEO, CIO, CTO, VP Operations, VP Sales, VP Marketing, etc.) and extract only their names and designations. Do not search the web for their emails or phone numbers; if these contact details are not explicitly present in the article text, set them as null.

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
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    tools=[{"google_search": {}}]
                )
            )
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
            competitor_names = {normalize_company_name(c['name']).strip().lower() for c in competitors if c.get('name')}
            
            # Fetch existing competitors for this pulse
            db_competitors = {comp.name.strip().lower() for comp in Competitor.objects.filter(pulse=pulse)}
            all_competitors = competitor_names | db_competitors

            # Insert Competitors first
            for comp in competitors:
                comp_name = normalize_company_name(comp['name'].strip())
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
                comp_name = normalize_company_name(c['name'].strip())
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
                lead_name = l.get('name', '').strip()
                org_name = normalize_company_name(l.get('organization_name', '')).strip()
                
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
                lead_name = l.get('name').strip()
                org_name = normalize_company_name(l.get('organization_name', '')).strip()
                
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

    print("Pulse summarization and lead extraction complete.")
