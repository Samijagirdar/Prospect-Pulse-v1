import os
import json
import sys

def call_gemini_api(raw_text):
    if 'test' in sys.argv:
        return None
        
    api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return None
        
    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        You are an elite GTM Sales Intelligence AI. Analyze the following text and extract precise business parameters for the target company/business.

        STRICT EXTRACTION INSTRUCTIONS:
        1. "employee_count": MUST be specific numeric figures or headcount ranges (e.g., "250 - 500", "1,200", "80 - 200"). NEVER return qualitative labels like "Small", "Medium", "Large", "Not specified", "Unknown", or "N/A". If not stated explicitly, estimate realistic numerical numbers based on industry knowledge.
        2. "revenue": MUST be specific numerical dollar ranges (e.g., "$15M - $50M", "$100M+", "$5M - $20M"). NEVER return vague text or "Not specified".
        3. "company_size": MUST be a specific headcount range with numbers (e.g., "100 - 500 Employees").
        4. "competitors": MUST list 3-5 real, legitimate, major direct market competitors that pose a real strategic threat to this company.
        5. "target_personas": MUST return a balanced mix of executive technology decision-makers AND revenue/sales/marketing leaders. Examples: "Chief Revenue Officer (CRO)", "VP of Sales", "Chief Technology Officer (CTO)", "Head of Sales Operations", "VP of Marketing", "Chief Commercial Officer".

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
        
        model_name = os.environ.get('GEMINI_MODEL') or 'gemini-3.5-flash'
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        
        if response.text:
            return json.loads(response.text)
    except Exception as e:
        print(f"Gemini API request failed: {e}")
        
    return None


