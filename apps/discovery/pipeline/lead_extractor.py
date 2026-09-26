import os
import json
import re

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
from apps.pulses.models import TargetCompetitor

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


def normalize_company_name(name):
    if not name:
        return ""
    name = name.strip()
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
    if not text:
        return "{}"
        
    cleaned = text.strip()
    first_brace = cleaned.find('{')
    if first_brace == -1:
        return "{}"
    
    candidate = cleaned[first_brace:]
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

    repaired = candidate
    if in_string:
        repaired += '"'
        in_string = False
        
    repaired = repaired.strip()
    
    while True:
        original = repaired
        repaired = re.sub(r',\s*$', '', repaired)
        repaired = re.sub(r'"[^"]*"\s*:\s*$', '', repaired)
        repaired = re.sub(r',\s*$', '', repaired)
        repaired = re.sub(r',\s*"[^"]*"\s*$', '', repaired)
        if repaired == original:
            break
            
    final_stack = []
    for c in repaired:
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if not in_string:
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

    json_candidate = extract_json_by_matching_braces(cleaned)
    try:
        return json.loads(json_candidate)
    except json.JSONDecodeError:
        pass

    json_candidate_fixed = re.sub(r',\s*([\}\]])', r'\1', json_candidate)
    try:
        return json.loads(json_candidate_fixed)
    except json.JSONDecodeError:
        pass

    try:
        repaired = repair_truncated_json(cleaned)
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    raise ValueError(f"Unable to parse valid JSON from LLM: {text[:200]}")


def extract_pulse_leads(pulse, discovery_run=None, articles_qs=None):
    """
    Extract target accounts (companies), competitors, and decision-maker leads
    for relevant articles in this pulse using Gemini with Google Search Grounding.
    """
    enable_gemini_leads = os.getenv("ENABLE_GEMINI_LEAD_EXTRACTION", "false").lower() == "true"
    if not enable_gemini_leads:
        print(f"[Lead Extractor] Gemini search grounding lead extraction is PAUSED (ENABLE_GEMINI_LEAD_EXTRACTION=false).")
        return 0, 0, 0, 0

    client = _get_client()

    if articles_qs is not None:
        articles = articles_qs
    elif discovery_run:
        articles = Article.objects.filter(discovery_run=discovery_run, is_relevant=True, is_duplicate=False)
    else:
        articles = Article.objects.filter(pulse=pulse, is_relevant=True, is_duplicate=False)

    if not articles.exists():
        print(f"Lead Extractor: No relevant articles found for pulse: {pulse.name}")
        return 0, 0, 0, 0

    print(f"Lead Extractor: Processing {articles.count()} relevant articles for pulse: {pulse.name}")

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    num_calls = 0

    model_name = os.getenv("GEMINI_LEAD_EXTRACTOR_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))

    pulse_name = (pulse.name or "").strip()
    profile = getattr(pulse, 'company_profile', None)
    target_account_focus = (getattr(profile, 'target_account_focus', None) or "").strip()
    target_industry = (getattr(profile, 'industry', None) or "").strip()
    ideal_champion = (getattr(profile, 'ideal_champion', None) or "").strip()
    personas_list = [p.role for p in pulse.personas_rel.all()] if hasattr(pulse, 'personas_rel') else []
    target_audience = ", ".join(personas_list) if personas_list else ideal_champion
    product_service = target_account_focus or target_industry or pulse_name
    industries_str = target_industry or "Technology, Cloud & Enterprise"
    value_proposition = target_account_focus or "Enterprise operational modernization and commercial adoption"
    competitor_names_list = ", ".join(pulse.competitors_list) or "None currently configured"
    target_geography = (pulse.target_geography or "").strip()

    for art in articles:
        if discovery_run:
            discovery_run.refresh_from_db(fields=['status'])
            if discovery_run.status == 'stopped':
                print(f"Lead Extractor: DiscoveryRun #{discovery_run.id} was stopped by user. Exiting lead extraction loop.")
                break

        title = art.title
        desc = art.description or ""
        art_id = art.id
        buying_signal = art.buying_signal or "General Intent"

        if target_geography:
            geo_section = f"""
**TARGET GEOGRAPHY (STRICT MANDATE)**:
{target_geography}
*CRITICAL MANDATE*: The user has specified that ONLY companies and leads headquartered in, located in, or actively operating within: {target_geography} must be targeted. If a company mentioned in the article is located outside {target_geography}, you MUST COMPLETELY IGNORE AND EXCLUDE it from the 'companies' and 'leads_mentioned' arrays.
"""
            geo_task = f"1. Extract EVERY company mentioned in the article that shows buyer/adopting intent AND is located or operating in {target_geography} (not just the primary subject) — score each 0-100 and map to an intent signal. Discard companies from other regions."
            geo_rule = f"- GEOGRAPHY RESTRICTION: You MUST ONLY extract companies and leads operating or headquartered in {target_geography}. Discard all companies from other regions."
        else:
            geo_section = """
**TARGET GEOGRAPHY**:
Global (No geographical restriction — companies and leads from all locations worldwide are accepted).
"""
            geo_task = "1. Extract EVERY company mentioned in the article that shows buyer/adopting intent (not just the primary subject) — score each 0-100 and map to an intent signal."
            geo_rule = "- GEOGRAPHY RESTRICTION: Global coverage (companies from any country or city are accepted)."

        prompt = f"""You are an elite sales and market intelligence agent equipped with Google Search grounding.
Analyze the following news article for our active discovery campaign and extract target accounts, competitors (both direct competitors and indirect alternatives), and key decision-maker leads.

**ACTIVE DISCOVERY CAMPAIGN PROFILE**:
- Campaign Name: {pulse_name}
- Product / Solution Domain: {product_service}
- Core Value Proposition: {value_proposition or 'Commercial and operational advancement in this industry'}
- Target Account Focus: {target_account_focus or 'Active enterprise growth, adoption, or expansion'}
- Target Buyer Personas: {target_audience or 'Executive leadership, VPs, and key technical decision-makers'}
- Target Industries: {industries_str or 'Cross-industry'}
- Known Monitored Competitors: {competitor_names_list}

{geo_section}

**ARTICLE TO ANALYZE**:
- Title: {title}
- Context Snippet: {desc}
- Article Intent Context: {buying_signal}

**TASKS**:
{geo_task}
2. COMPETITOR IDENTIFICATION & STRATEGIC MOVES TRACKING:
   Identify any company mentioned in the article that operates on the vendor/solution provider side in this market space. Classify as a competitor if:
   a) DIRECT COMPETITOR: It offers directly competing products, services, or solutions within the domain of this campaign ({product_service}), OR it matches a company in the Known Monitored Competitors list above. Set "competitor_type": "direct".
   b) INDIRECT COMPETITOR / ALTERNATIVE: It provides an alternative approach, substitute technology, or adjacent service that addresses the same core problem or competes for the same customer budget as {product_service}. Set "competitor_type": "indirect".
   For each competitor identified, classify their exact STRATEGIC MOVE or ACTIVITY in "buying_signal". You can choose from standard categories such as:
   - "Fundraising / Capital Raise" (e.g., raised venture capital, private equity, debt round, IPO)
   - "New Leadership / Executive Hiring" (e.g., appointed new CEO, CTO, VP, board appointments)
   - "Product Launch / Feature Release" (e.g., launched new product, AI capability, platform update)
   - "Strategic Partnership / Alliance" (e.g., partnership, integration, joint go-to-market)
   - "Mergers & Acquisitions (M&A)" (e.g., acquired a competitor or company, merger)
   - "Market & Geographic Expansion" (e.g., entered new region, opened office, expanded facilities)
   - "Competing Solution / Market Activity"
   OR, if the move does not fit into these standard categories, explicitly name a clear, professional custom category (e.g., "Major Contract Win / Enterprise Deal", "Patent / IP Approval", "Rebranding / Strategic Pivot", "Regulatory & Compliance Milestone", "Pricing & Business Model Change", "Restructuring / Operational Shift").
   In "reason", provide a concise, factual summary explaining their specific strategic move and competitive impact (e.g. "[Company] is expanding its [capabilities] to offer [features], directly competing with our [domain] solution offerings"). CRITICAL MANDATE: Do NOT include "[Direct Competitor]" or "[Indirect Alternative]" in the "reason" field itself; the classification is captured separately in "competitor_type".
   Competitors MUST NOT appear in the 'companies' array — list them ONLY in 'competitors'.
3. DECISION-MAKER DISCOVERY:
   For all extracted target accounts showing commercial intent, use Google Search to find current executive leadership and key decision-makers (such as CEO, CIO, CTO, VP Operations, VP Sales, VP Marketing, Head of Engineering, Technical Lead, Solutions Architect, IT Manager matching {target_audience}) and extract only their names and exact designations. Do not guess emails or phone numbers; if not explicitly found, set them as null.

**RULES**:
{geo_rule}
- Assign buyer intent scores (80-100) for active expansion, hiring, investment, or new technology adoption; lower (40-70) for thought leadership or general news.
- Ensure that designations represent standard job titles (e.g. CIO, VP Sales, Head of Engineering).
- Do not list competitors in the 'companies' or 'leads_mentioned' arrays.

Return your answer as a JSON object matching this structure EXACTLY:
{{
  "companies": [
     {{
       "name": "Company Name",
       "score": 0-100,
       "buying_signal": "intent signal name",
       "reason": "explanation of commercial intent"
     }}
  ],
  "competitors": [
     {{
       "name": "Competitor Company Name",
       "competitor_type": "direct" | "indirect",
       "matched_known_competitor": true | false,
       "buying_signal": "Standard Category (Fundraising, Leadership, Product Launch, Partnership, M&A, Expansion) OR explicit custom move name (e.g. Major Contract Win, Regulatory Milestone, Strategic Pivot)",
       "reason": "Specific strategic move or development described in this article and its competitive significance"
     }}
  ],
  "leads_mentioned": [
     {{
       "name": "Full Name",
       "designation": "Job Title",
       "organization_name": "Target Account Name",
       "score": 0-100,
       "buying_signal": "intent signal",
       "reason": "why they are a relevant decision-maker",
       "email": null,
       "phone": null
     }}
  ]
}}
"""

        try:
            response = None
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        tools=[{"google_search": {}}],
                        max_output_tokens=3072
                    )
                )
                if not response or not response.text:
                    raise ValueError("Empty response text from search-grounded model")
            except Exception as first_err:
                print(f"Lead Extractor: Search grounding attempt failed ({first_err}). Retrying without search tool...")
                fallback_prompt = prompt.replace("equipped with Google Search grounding", "analyzing B2B leadership")
                fallback_prompt = fallback_prompt.replace(
                    "use Google Search to find their key decision-makers and technical influencers",
                    "extract key decision-makers and technical influencers directly from the article text or your knowledge base"
                )
                response = client.models.generate_content(
                    model=model_name,
                    contents=fallback_prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=3072
                    )
                )
                if not response or not response.text:
                    raise ValueError("Empty response text on retry without search tool")

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

            print(f"[Gemini 3.8 Lead Extractor] Article #{art_id} | In: {prompt_tokens} | Out: {completion_tokens} | Total: {tot_tokens} tokens", flush=True)

            res_json = clean_and_parse_json(response.text)

            companies = res_json.get("companies", [])
            competitors = res_json.get("competitors", [])
            leads = res_json.get("leads_mentioned", []) or res_json.get("leads", [])

            # Enforce mutual exclusivity
            competitor_names = {normalize_company_name(c.get('name') or '').strip().lower() for c in competitors if c.get('name')}
            db_competitors = {comp.name.strip().lower() for comp in Competitor.objects.filter(pulse=pulse)}
            all_competitors = competitor_names | db_competitors

            # 1. Insert Competitors first
            for comp in competitors:
                raw_name = comp.get('name')
                if not raw_name:
                    continue
                comp_name = normalize_company_name(str(raw_name).strip())
                if not comp_name:
                    continue

                comp_type = str(comp.get('competitor_type') or 'direct').lower()
                c_type = 'indirect' if 'indirect' in comp_type else 'direct'
                raw_reason = comp.get('reason') or f"{comp_name} was identified as an active vendor in this market space."
                clean_reason = re.sub(r'^\[(Direct Competitor|Indirect Alternative)\]\s*', '', str(raw_reason), flags=re.IGNORECASE).strip()
                sig_val = comp.get('buying_signal') or f"{c_type.capitalize()} Competitor Signal"

                try:
                    Competitor.objects.update_or_create(
                        pulse=pulse,
                        name=comp_name,
                        source_article=art,
                        defaults={
                            'competitor_type': c_type,
                            'buying_signal': sig_val,
                            'reason': clean_reason,
                            'source_article': art,
                            'discovery_run': discovery_run
                        }
                    )
                    # Automatically register in pulse's TargetCompetitor so future scrapers actively monitor it
                    if not TargetCompetitor.objects.filter(pulse=pulse, competitor_name__iexact=comp_name).exists():
                        TargetCompetitor.objects.create(
                            pulse=pulse,
                            competitor_name=comp_name
                        )

                    # Keep lists mutually exclusive
                    Company.objects.filter(pulse=pulse, name__iexact=comp_name).delete()
                    Lead.objects.filter(pulse=pulse, organization_name__iexact=comp_name).delete()
                except Exception as ce:
                    print(f"Error saving competitor {comp_name}: {ce}")

            # 2. Insert Companies (excluding competitors)
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

            # 3. Deduplicate leads at memory level and filter invalid names
            unique_leads = []
            seen_leads = set()
            for l in leads:
                lead_name = (l.get('name') or '').strip()
                org_name = normalize_company_name(l.get('organization_name') or '').strip()
                if not lead_name or not org_name:
                    continue
                if is_invalid_name(lead_name):
                    print(f"Excluding lead with placeholder name: '{lead_name}' at '{org_name}'")
                    continue
                key = (lead_name.lower(), org_name.lower())
                if key in seen_leads:
                    continue
                seen_leads.add(key)
                unique_leads.append(l)

            # 4. Insert Leads
            for l in unique_leads:
                lead_name = (l.get('name') or '').strip()
                org_name = normalize_company_name(l.get('organization_name') or '').strip()
                if not lead_name:
                    continue
                if org_name.lower() in all_competitors:
                    print(f"Excluding lead '{lead_name}' because organization '{org_name}' is classified as a competitor.")
                    continue
                if Lead.objects.filter(pulse=pulse, name__iexact=lead_name, organization_name__iexact=org_name).exists():
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

            print(f"Lead Extractor: Processed article #{art_id} ('{title[:40]}...') -> Accounts and leads extracted.")

        except Exception as e:
            print(f"Error extracting leads for article #{art_id}: {e}")
            # Non-fatal for the entire run: log and continue to next article
            continue

    print("Pulse lead & account extraction stage complete.")
    return total_prompt_tokens, total_completion_tokens, total_tokens, num_calls


def extract_leads_for_company(pulse, company, article=None):
    """
    Extracts decision-maker leads for a specific company matching the pulse's ICP.
    Invoked when a user promotes a competitor to a target company ('Move to Target').
    Uses Gemini 3.8 Flash with Google Search grounding.
    """
    if not company or not company.name:
        return []

    raw_comp_name = company.name.strip()
    norm_comp_name = normalize_company_name(raw_comp_name)
    if not norm_comp_name:
        return []

    try:
        client = _get_client()
    except Exception as err:
        print(f"Cannot initialize Gemini client for company lead extraction: {err}")
        return []

    profile = getattr(pulse, 'company_profile', None)
    target_account_focus = getattr(profile, 'target_account_focus', '') or ''
    target_industry = getattr(profile, 'industry', '') or ''
    ideal_champion = getattr(profile, 'ideal_champion', '') or ''
    personas_list = [p.role for p in pulse.personas_rel.all()] if hasattr(pulse, 'personas_rel') else []
    target_audience = ", ".join(personas_list) if personas_list else ideal_champion or "Executive Decision-Makers"
    product_service = target_account_focus or target_industry or (pulse.name or '')
    value_proposition = target_account_focus or "Enterprise operational modernization"

    art = article or getattr(company, 'source_article', None)
    if not art:
        art = Article.objects.filter(pulse=pulse).first()

    # Try Disburse.dev first for instant, grounded contact intelligence
    try:
        from .disburse_client import DisburseClient
        disburse_client = DisburseClient()
        if disburse_client.is_configured:
            target_geography = (getattr(pulse, 'target_geography', None) or "").strip()
            disburse_results = disburse_client.search_leads_for_company(
                company_name=raw_comp_name,
                personas=personas_list,
                country=target_geography,
                limit=3
            )
            if disburse_results:
                print(f"[Disburse] Found {len(disburse_results)} leads for company {raw_comp_name}")
                disburse_created = []
                for item in disburse_results:
                    lname = (item.get("name") or "").strip()
                    ltitle = (item.get("title") or item.get("headline") or "").strip()
                    lorg = (item.get("company_name") or item.get("company_display_name") or raw_comp_name).strip()
                    lemail = (item.get("email") or "").strip() or None
                    lphone = (item.get("direct_phone") or item.get("cellphone") or item.get("phone") or item.get("company_phone") or "").strip() or None
                    llinkedin = (item.get("linkedin_url") or "").strip()

                    if not lname or is_invalid_name(lname):
                        continue
                    if Lead.objects.filter(pulse=pulse, name__iexact=lname, organization_name__iexact=lorg).exists():
                        continue

                    lreason = f"Verified executive at {lorg} via Disburse (Matched Personas: {target_audience})"
                    if llinkedin:
                        lreason += f" | LinkedIn: {llinkedin}"

                    try:
                        dl = Lead.objects.create(
                            pulse=pulse,
                            discovery_run=getattr(company, 'discovery_run', None),
                            source_article=art,
                            name=lname,
                            designation=ltitle,
                            organization_name=lorg,
                            score=getattr(company, 'score', 80) or 80,
                            buying_signal=getattr(company, 'buying_signal', 'Target account decision maker') or 'Target account decision maker',
                            reason=lreason,
                            email=lemail,
                            phone=lphone,
                            linkedin_url=llinkedin or None
                        )

                        disburse_created.append(dl)
                    except Exception as cle:
                        print(f"Error creating Disburse lead {lname}: {cle}")
                if disburse_created:
                    return disburse_created
    except Exception as d_err:
        print(f"[Disburse] Failed company lead search: {d_err}.")

    enable_gemini_leads = os.getenv("ENABLE_GEMINI_LEAD_EXTRACTION", "false").lower() == "true"
    if not enable_gemini_leads:
        print(f"[Lead Extractor] Gemini lead extraction is disabled/paused (ENABLE_GEMINI_LEAD_EXTRACTION=false). Skipping Gemini search for '{raw_comp_name}'.")
        return []

    article_context = ""
    if art:


        art_title = getattr(art, 'title', '') or ''
        art_content = getattr(art, 'description', '') or ''
        article_context = f"\nRelated Article Context:\nTitle: {art_title}\nSnippet: {art_content[:1500]}"

    prompt = f"""You are an elite sales and market intelligence agent with access to Google Search grounding.
Find 2 to 4 current key decision-makers and technical influencers involved in evaluation or leadership for the company "{raw_comp_name}".
Context:
- Our Solution / Product: {product_service}
- Target Buyer Profiles: {target_audience}
- Value Proposition: {value_proposition}
{article_context}

INSTRUCTIONS:
1. Use Google Search to find real executive names and their exact job titles at "{raw_comp_name}" (e.g. CEO, CTO, CIO, VP Sales, VP Engineering, Head of Operations, Director of Product, IT Director, etc.).
2. Extract ONLY their full name and designation. Do NOT guess or hallucinate emails/phone numbers (set them to null).
3. Provide a realistic buying score (60-95) and rationale for why this person is a key lead.
4. Output MUST be valid JSON matching this schema:
{{
  "leads": [
    {{
      "name": "Full Name",
      "designation": "Job Title",
      "organization_name": "{raw_comp_name}",
      "score": 85,
      "buying_signal": "Executive leadership at target account",
      "reason": "Why they are a relevant decision maker",
      "email": null,
      "phone": null
    }}
  ]
}}
"""

    model_name = os.getenv("GEMINI_LEAD_EXTRACTOR_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))

    response = None
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                tools=[{"google_search": {}}],
                max_output_tokens=2048
            )
        )
        if not response or not response.text:
            raise ValueError("Empty response from search-grounded model")
    except Exception as first_err:
        print(f"extract_leads_for_company: First attempt with search grounding failed: {first_err}. Retrying without search grounding...")
        try:
            fallback_prompt = prompt.replace("with access to Google Search grounding", "analyzing B2B leadership")
            fallback_prompt = fallback_prompt.replace(
                "Use Google Search to find real executive names and their exact job titles",
                "Extract or identify key leadership roles and executive names from your knowledge base"
            )
            response = client.models.generate_content(
                model=model_name,
                contents=fallback_prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=2048
                )
            )
        except Exception as retry_err:
            print(f"extract_leads_for_company: Retry without search grounding failed: {retry_err}")
            return []

    if not response or not response.text:
        return []

    try:
        res_json = clean_and_parse_json(response.text)
    except Exception as pe:
        print(f"Failed to parse JSON for company lead extraction: {pe}")
        return []

    leads_data = res_json.get("leads", []) or res_json.get("leads_mentioned", [])
    if not isinstance(leads_data, list):
        return []

    db_competitors = {comp.name.strip().lower() for comp in Competitor.objects.filter(pulse=pulse)}
    if norm_comp_name.lower() in db_competitors:
        print(f"Company '{norm_comp_name}' is still in competitors list. Skipping lead creation.")
        return []

    if not art:
        art = Article.objects.filter(pulse=pulse).first()
        if not art:
            art = Article.objects.create(
                pulse=pulse,
                title=f"Intelligence Profile - {norm_comp_name}",
                url="",
                source="Target Account Lead Discovery"
            )

    created_leads = []
    seen = set()

    for l in leads_data:
        if not isinstance(l, dict):
            continue
        lead_name = (l.get('name') or '').strip()
        if not lead_name or is_invalid_name(lead_name):
            continue

        org_name = normalize_company_name((l.get('organization_name') or raw_comp_name).strip())
        if not org_name:
            org_name = norm_comp_name

        key = (lead_name.lower(), org_name.lower())
        if key in seen:
            continue
        seen.add(key)

        if Lead.objects.filter(pulse=pulse, name__iexact=lead_name, organization_name__iexact=org_name).exists():
            continue

        try:
            new_lead = Lead.objects.create(
                pulse=pulse,
                discovery_run=getattr(company, 'discovery_run', None),
                source_article=art,
                name=lead_name,
                designation=l.get('designation') or '',
                organization_name=org_name,
                score=l.get('score', 75),
                buying_signal=l.get('buying_signal') or company.buying_signal or 'Target account decision maker',
                reason=l.get('reason') or company.reason or f'Key decision maker at {norm_comp_name}',
                email=l.get('email') or None,
                phone=l.get('phone') or None
            )
            created_leads.append(new_lead)
        except Exception as cle:
            print(f"Error creating lead {lead_name}: {cle}")

    return created_leads
