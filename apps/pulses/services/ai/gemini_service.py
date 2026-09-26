import os
import json
import sys
import re

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
    
    # Strip markdown code blocks
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()
        
    # First, try standard JSON extraction and parsing
    json_candidate = extract_json_by_matching_braces(cleaned)
    try:
        return json.loads(json_candidate)
    except json.JSONDecodeError:
        pass
        
    # Second, try trailing comma repair
    json_candidate_fixed = re.sub(r',\s*([\}\]])', r'\1', json_candidate)
    try:
        return json.loads(json_candidate_fixed)
    except json.JSONDecodeError:
        pass
        
    # Third, run full structural truncation repair
    json_repaired = repair_truncated_json(cleaned)
    try:
        return json.loads(json_repaired)
    except json.JSONDecodeError as e:
        raise ValueError(f"Unable to parse valid JSON from LLM: {str(e)}\nRaw Response: {text[:200]}")

def call_gemini_api(raw_text, company_name=None, website_url=None, target_geography=None):
    if 'test' in sys.argv:
        return None
        
    api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("Google API Key or Gemini API Key is not set in environment variables.")
        
    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=api_key)
        
        company_meta = []
        if company_name and company_name.strip():
            company_meta.append(f"- Company/Product Name: {company_name.strip()}")
        if website_url and website_url.strip():
            company_meta.append(f"- Website URL: {website_url.strip()}")
        if target_geography and target_geography.strip():
            company_meta.append(f"- Target Geography: {target_geography.strip()}")
        meta_block = "\n".join(company_meta) if company_meta else "- Company: Extracted from provided source text"

        prompt = f"""
        You are an elite GTM Sales Intelligence AI with access to Google Search grounding.
        Analyze the company profile, offering, and website text below to extract precise GTM parameters, Ideal Customer Profile (ICP), target accounts focus, and competitive intelligence.

        Company Context:
        {meta_block}

        If parameters like employee count, revenue, target focus, or competitors are not explicitly stated in the source text, use Google Search to research the company ({company_name or 'the company associated with this domain'}) online to determine accurate, high-fidelity values. Do not guess or output generic/irrelevant values.

        STRICT EXTRACTION INSTRUCTIONS:
        1. "industry": Must be the true core industry of what the company's product or service actually does (e.g. "AI Sales Automation & Revenue Operations", "Cybersecurity & MSSP", "Cloud Data Infrastructure", etc.).
        2. "target_account_focus_chips": 4-5 specific capability or solution chips that this company actually sells or solves (e.g. for sales platforms: "Autonomous Sales Operations (ASOC)", "AI BDR & Outreach", "Pipeline Acceleration", "Speed-to-Lead Automation").
        3. "employee_count": MUST be specific numeric figures or headcount ranges (e.g., "250 - 500", "1,200", "80 - 200"). NEVER return qualitative labels like "Small", "Medium", "Large", "Not specified", "Unknown", or "N/A".
        4. "revenue": MUST be specific numerical dollar ranges (e.g., "$15M - $50M", "$100M+", "$5M - $20M"). NEVER return vague text or "Not specified".
        5. "company_size": MUST be a specific headcount range with numbers (e.g., "100 - 500 Employees").
        6. "competitors": MUST list 3-5 real, legitimate, direct market competitors that compete against this company's core product/service in the same space.
        7. "target_personas": MUST return a balanced mix of executive buyers and decision-makers who would purchase this company's product (e.g. "Chief Revenue Officer (CRO)", "VP of Sales", "Chief Technology Officer (CTO)", "Head of Sales Operations", "VP of Marketing").

        Return ONLY a JSON object matching this exact schema:

        {{
          "company_summary": {{
            "industry": "Specific Industry Sector",
            "company_size": "100 - 500 Employees",
            "employee_count": "250 - 500",
            "revenue": "$10M - $50M",
            "region": "Primary Operating Region"
          }},
          "target_account_focus_chips": [
            "List of 4-5 GTM focus chips"
          ],
          "target_personas": [
            "Mix of CRO, CTO, VP Sales, VP Marketing, Head of Sales Ops"
          ],
          "pain_points": [
            "List of key operational pain points"
          ],
          "competitors": [
            "List of real direct market competitors"
          ],
          "categorized_keywords": {{
            "Primary Discovery": ["Array of search keywords (Max 5)"],
            "Secondary Discovery": ["Array of keywords (Max 5)"]
          }},
          "categorized_buying_signals": {{
            "Organizational": ["Array of events (Max 4)"],
            "Technology": ["Array of events (Max 4)"],
            "Business": ["Array of events (Max 4)"]
          }},
          "tech_stack": [
            "List of core technologies"
          ],
          "confidence_score": 94,
          "confidence_reason": "High-confidence GTM parameter extraction"
        }}

        Source text content:
        {raw_text}
        """
        
        primary_model = os.environ.get('GEMINI_ICP_MODEL') or os.environ.get('GEMINI_MODEL') or 'gemini-3.8-flash'
        fallback_model = os.environ.get('GEMINI_BACKUP_MODEL') or 'gemini-3.7-flash'

        use_search_tool = bool(len(raw_text.strip()) < 300)
        tools_config = [{"google_search": {}}] if use_search_tool else None

        try:
            response = client.models.generate_content(
                model=primary_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    tools=tools_config,
                    max_output_tokens=4096
                ),
            )
            if not response.text:
                raise ValueError("Empty response text from LLM")
        except Exception as first_err:
            print(f"Gemini GTM enrichment: Primary model {primary_model} failed ({first_err}). Retrying with {fallback_model}...")

            
            # Define fallback prompt without Google Search grounding instructions
            fallback_prompt = prompt.replace("with access to Google Search grounding", "analyzing GTM inputs")
            fallback_prompt = fallback_prompt.replace(
                "If parameters like employee count, revenue, target focus, or competitors are not explicitly stated in the source text, use Google Search to research the company (or the company that owns the website URL) online and find the exact or nearly exact values. Do not guess or output random/default values.",
                "If parameters are not explicitly stated, estimate realistic numerical numbers based on your internal training knowledge of the company."
            )
            
            response = client.models.generate_content(
                model=fallback_model,
                contents=fallback_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=4096
                ),
            )
            if not response.text:
                raise ValueError("Empty response text from LLM on retry")
        
        # Extract token usage and print to console
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
            completion_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0
            total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) or (prompt_tokens + completion_tokens)
        
        print(f"\n[Gemini API] Call: GTM Profile Enrichment | Prompt: {prompt_tokens} | Completion: {completion_tokens} | Total: {total_tokens} tokens\n")
        
        return clean_and_parse_json(response.text)
    except Exception as e:
        print(f"Gemini API request failed: {e}")
        raise e


def enrich_missing_gtm_params(name, description, industries, value_props, existing_data):
    """
    Call Gemini to generate optimized search keywords, and also enrich
    any fields that are missing or empty in the existing GTM profile data.
    """
    if 'test' in sys.argv:
        # Mock values for offline testing
        return {
            "industry": existing_data.get("industry") or "Logistics",
            "company_size": existing_data.get("company_size") or "100 - 500 Employees",
            "revenue_range": existing_data.get("revenue_range") or "$10M - $50M",
            "employee_count": existing_data.get("employee_count") or "250 - 500",
            "target_account_focus": existing_data.get("target_account_focus") or "Supply Chain Optimization",
            "ideal_champion": existing_data.get("ideal_champion") or "CISO, IT Director",
            "tech_stack": existing_data.get("tech_stack") or "Salesforce, SAP",
            "personas": existing_data.get("personas") or [],
            "competitors": existing_data.get("competitors") or ["CompetitorA", "CompetitorB"],
            "buying_signals": existing_data.get("buying_signals") or ["Recent Series A Funding"],
            "categorized_keywords": {
                "Primary Discovery": ["cloud security", "cybersecurity compliance"],
                "Secondary Discovery": ["threat intelligence", "risk management"]
            }
        }
        
    api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("Google API Key or Gemini API Key is not set in environment variables.")
        
    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=api_key)
        
        # Serialize existing data for prompt context
        existing_json = json.dumps(existing_data, indent=2)
        
        prompt = f"""
        You are an elite GTM Sales Intelligence AI. Based on the following Go-To-Market (GTM) Strategy details, generate the RSS search keywords AND complete any target parameters that are missing, blank, or empty in the campaign details.

        GTM Campaign Template Details:
        - Campaign Name: {name}
        - Description/Notes: {description}
        - Target Industries: {industries}
        - Value Propositions: {value_props}

        Current Stored Parameters (Priority):
        {existing_json}

        INSTRUCTIONS:
        1. "categorized_keywords" (Primary & Secondary Discovery, max 5 keywords each) MUST be generated from scratch since keywords are not present in GTM templates.
        2. Inspect all other fields in the "Current Stored Parameters". If any field is empty, null, or has default placeholders, use Google Search grounding or your GTM intelligence to enrich it with high-confidence, realistic values. If a field already has a valid value, keep it.
        3. "employee_count", "company_size", and "revenue_range" MUST be numeric ranges if missing (e.g. "100 - 500", "$10M - $50M"). Do not output vague qualitative labels.
        4. "competitors" MUST list 3-5 real direct market competitors if the current list is empty.
        5. "personas" MUST return a balanced array of decision-maker dicts (role, type, responsibilities, goals, roadblocks, pain_points) if the current list is empty.

        Return ONLY a JSON object matching this exact schema:
        {{
          "industry": "Target Industry",
          "company_size": "Headcount description (e.g. 100 - 500 Employees)",
          "revenue_range": "Revenue range (e.g. $10M - $50M)",
          "employee_count": "Numeric headcount (e.g. 100 - 250)",
          "target_account_focus": "Target account focus vertical/products",
          "ideal_champion": "Ideal champion executive roles",
          "tech_stack": "Core tech stack technologies",
          "competitors": ["List of competitors"],
          "buying_signals": ["List of buying signals/intent triggers"],
          "personas": [
            {{
              "role": "Job Title (e.g. CISO)",
              "type": "Economic Buyer or Technical Champion",
              "responsibilities": "Job responsibilities description",
              "goals": "Core job goals description",
              "roadblocks": "Main job challenges description",
              "pain_points": ["List of pain points"]
            }}
          ],
          "categorized_keywords": {{
            "Primary Discovery": ["Array of search keywords (Max 5)"],
            "Secondary Discovery": ["Array of keywords (Max 5)"]
          }}
        }}
        """
        
        primary_model = os.environ.get('GEMINI_ICP_MODEL') or os.environ.get('GEMINI_MODEL') or 'gemini-3.8-flash'
        fallback_model = os.environ.get('GEMINI_BACKUP_MODEL') or 'gemini-3.7-flash'
        try:
            response = client.models.generate_content(
                model=primary_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=4096
                ),
            )
            if not response.text:
                raise ValueError("Empty response text from LLM")
        except Exception as first_err:
            print(f"Gemini GTM enrichment: Primary model {primary_model} failed ({first_err}). Retrying with {fallback_model}...")
            response = client.models.generate_content(
                model=fallback_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=4096
                ),
            )
            if not response.text:
                raise ValueError("Empty response text from LLM on retry")
            
        # Extract token usage and print to console
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
            completion_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0
            total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) or (prompt_tokens + completion_tokens)
        
        print(f"\n[Gemini API] Call: GTM Parameter Enrichment | Prompt: {prompt_tokens} | Completion: {completion_tokens} | Total: {total_tokens} tokens\n")
        
        return clean_and_parse_json(response.text)
    except Exception as e:
        print(f"Gemini GTM parameter enrichment failed: {e}")
        raise e



