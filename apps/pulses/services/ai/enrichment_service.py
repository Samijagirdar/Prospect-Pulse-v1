from . import pdf_service, url_service, gemini_service
from ...models import Pulse, CompanyProfile, Persona, TargetCompetitor, Keyword, BuyingSignal

def save_ai_pulse_insights_orm(pulse, company_profile_data, personas_data, competitors_data, keywords_data, buying_signals_data):
    # Upsert CompanyProfile
    CompanyProfile.objects.update_or_create(
        pulse=pulse,
        defaults={
            'industry': company_profile_data.get('industry', ''),
            'company_size': company_profile_data.get('company_size', ''),
            'revenue_range': company_profile_data.get('revenue_range', ''),
            'employee_count': company_profile_data.get('employee_count', ''),
            'target_account_focus': company_profile_data.get('target_account_focus', ''),
            'ideal_champion': company_profile_data.get('ideal_champion', ''),
            'tech_stack': company_profile_data.get('tech_stack', ''),
            'ai_confidence_score': company_profile_data.get('ai_confidence_score', 90),
            'ai_confidence_reason': company_profile_data.get('ai_confidence_reason', '')
        }
    )
    
    # Delete old personas and recreate
    pulse.personas_rel.all().delete()
    for persona in personas_data:
        Persona.objects.create(
            pulse=pulse,
            role=persona['role'],
            type=persona.get('type', ''),
            responsibilities=persona.get('responsibilities', ''),
            goals=persona.get('goals', ''),
            roadblocks=persona.get('roadblocks', ''),
            pain_points=",".join(persona.get('pain_points', []))
        )
        
    # Delete old competitors and recreate
    pulse.competitors.all().delete()
    for comp in competitors_data:
        TargetCompetitor.objects.create(pulse=pulse, competitor_name=comp)
        
    # Delete old keywords and recreate
    pulse.keywords_rel.all().delete()
    for cat, list_kws in keywords_data.items():
        if isinstance(list_kws, list):
            for kw in list_kws:
                Keyword.objects.create(pulse=pulse, keyword=kw, category=cat)
                
    # Delete old buying signals and recreate
    pulse.buying_signals_rel.all().delete()
    for cat, list_sigs in buying_signals_data.items():
        if isinstance(list_sigs, list):
            for sig in list_sigs:
                BuyingSignal.objects.create(pulse=pulse, signal_name=sig, category=cat)


def ensure_numeric_estimate(val: str, default_val: str) -> str:
    if not val:
        return default_val
    val_clean = str(val).strip()
    vague_terms = ["small", "medium", "large", "not specified", "unknown", "n/a", "none", "big", "micro", "enterprise"]
    if any(t in val_clean.lower() for t in vague_terms) and not any(char.isdigit() for char in val_clean):
        return default_val
    return val_clean


def generate_ai_pulse_insights(pulse):
    raw_text = ""
    
    if pulse.input_type == 'pdf' and pulse.pdf_file:
        raw_text = pdf_service.extract_text_from_pdf(pulse.pdf_file)
    elif pulse.input_type == 'url' and pulse.url:
        raw_text = url_service.extract_text_from_url(pulse.url)
    elif pulse.input_type == 'text' and pulse.text_content:
        raw_text = pulse.text_content
    elif pulse.input_type == 'icp' and pulse.from_document_id:
        import json
        from django.db import connection
        
        # 1. Fetch from gtm_gtmplan via raw SQL to support prod environment without GtmPlan model
        row = None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name, notes, icp_definition, buyer_personas, target_industries, value_propositions, product_offerings, target_companies "
                    "FROM gtm_gtmplan WHERE id = %s",
                    [pulse.from_document_id]
                )
                row = cursor.fetchone()
        except Exception as e:
            raise ValueError(f"Failed to query gtm_gtmplan database table: {e}")
            
        if not row:
            raise ValueError(f"Selected GTM Plan/ICP template with ID {pulse.from_document_id} does not exist.")
            
        # Parse fields from the DB row
        name = row[0] or ""
        notes = row[1] or ""
        icp_def = json.loads(row[2]) if row[2] else {}
        buyer_personas_list = json.loads(row[3]) if row[3] else []
        target_industries = json.loads(row[4]) if row[4] else []
        value_propositions = json.loads(row[5]) if row[5] else []
        product_offerings = json.loads(row[6]) if row[6] else []
        target_companies = json.loads(row[7]) if row[7] else []
        
        # 2. Extract values from DB GTM strategy template
        industry_str = ", ".join(target_industries) if isinstance(target_industries, list) else str(target_industries)
        if not industry_str:
            industry_str = icp_def.get('industry', '')
            
        tech = icp_def.get('technology_stack', [])
        tech_str = ", ".join(tech) if isinstance(tech, list) else str(tech)
        
        ideal_champ = icp_def.get('ideal_buyer_persona') or ", ".join([p.get('title', '') for p in buyer_personas_list[:2]])
        
        # Format existing personas
        personas_data = []
        for idx, bp in enumerate(buyer_personas_list):
            goals = bp.get('goals') or []
            goals_str = ", ".join(goals) if isinstance(goals, list) else str(goals)
            resp = bp.get('responsibilities') or []
            resp_str = ", ".join(resp) if isinstance(resp, list) else str(resp)
            challenges = bp.get('challenges') or []
            challenges_str = ", ".join(challenges) if isinstance(challenges, list) else str(challenges)
            
            personas_data.append({
                'role': bp.get('title') or f"Persona {idx+1}",
                'type': bp.get('role') or ('Economic Buyer' if idx == 0 else 'Technical Champion'),
                'responsibilities': resp_str,
                'goals': goals_str,
                'roadblocks': challenges_str,
                'pain_points': bp.get('pain_points') or []
            })
            
        # Target competitors
        competitors_data = target_companies[:8] if isinstance(target_companies, list) else []
        
        # Buying Signals
        buying_signals_list = icp_def.get('buying_signals') or []
        
        # Compile existing profile dictionary to send to Gemini (identifying what is missing)
        existing_data = {
            'industry': industry_str,
            'company_size': icp_def.get('company_size', ''),
            'revenue_range': icp_def.get('revenue_range', ''),
            'employee_count': icp_def.get('employee_count', ''),
            'target_account_focus': ", ".join(product_offerings),
            'ideal_champion': ideal_champ,
            'tech_stack': tech_str,
            'competitors': competitors_data,
            'buying_signals': buying_signals_list,
            'personas': personas_data
        }
        
        # 3. Call Gemini to enrich missing parameters AND generate RSS search keywords
        print("Calling Gemini API to enrich missing parameters and generate target RSS search keywords...")
        enriched = gemini_service.enrich_missing_gtm_params(
            name=name,
            description=notes,
            industries=industry_str,
            value_props=", ".join(value_propositions),
            existing_data=existing_data
        )
        
        # 4. Merge parameters prioritizing DB values and falling back to Gemini-enriched values for empty fields
        merged_profile = {
            'industry': existing_data['industry'] or enriched.get('industry') or 'Enterprise B2B Technology',
            'company_size': existing_data['company_size'] or enriched.get('company_size') or '100 - 500 Employees',
            'revenue_range': existing_data['revenue_range'] or enriched.get('revenue_range') or '$10M - $50M',
            'employee_count': existing_data['employee_count'] or enriched.get('employee_count') or '150 - 500',
            'target_account_focus': existing_data['target_account_focus'] or enriched.get('target_account_focus') or '',
            'ideal_champion': existing_data['ideal_champion'] or enriched.get('ideal_champion') or 'Chief Revenue Officer',
            'tech_stack': existing_data['tech_stack'] or enriched.get('tech_stack') or '',
            'ai_confidence_score': 95,
            'ai_confidence_reason': 'Prefetched from GtmPlan database template with Gemini parameter enrichment.'
        }
        
        # Merge Personas: if DB list is empty, use Gemini's personas
        final_personas = existing_data['personas'] if existing_data['personas'] else enriched.get('personas') or []
        
        # Merge Competitors: if DB list is empty, use Gemini's competitors
        final_competitors = existing_data['competitors'] if existing_data['competitors'] else enriched.get('competitors') or []
        
        # Merge Buying Signals: if DB list is empty, use Gemini's buying signals
        final_buying_signals = existing_data['buying_signals'] if existing_data['buying_signals'] else enriched.get('buying_signals') or []
        buying_signals_data = {
            'Business': final_buying_signals
        }
        
        # Keywords generated by Gemini
        keywords_data = enriched.get('categorized_keywords') or {
            'Primary Discovery': [],
            'Secondary Discovery': []
        }
        
        # Save to database
        save_ai_pulse_insights_orm(pulse, merged_profile, final_personas, final_competitors, keywords_data, buying_signals_data)
        
        # Populate text_content with a summary preview of the ICP definition
        pulse.text_content = f"GTM Campaign Template: {name}\n\nTarget ICP Definition:\n{json.dumps(icp_def, indent=2)}"
        pulse.save()
        return

        
    result = None
    if raw_text.strip():
        result = gemini_service.call_gemini_api(raw_text)
        
    if result:
        summary = result.get('company_summary') or {}
        
        raw_emp = summary.get('employee_count') or summary.get('company_size')
        raw_size = summary.get('company_size') or summary.get('employee_count')
        raw_rev = summary.get('revenue')
        
        emp_count = ensure_numeric_estimate(raw_emp, "150 - 500")
        comp_size = ensure_numeric_estimate(raw_size, "100 - 500 Employees")
        rev_range = ensure_numeric_estimate(raw_rev, "$10M - $50M")
        
        comp_profile = {
            'industry': summary.get('industry') or 'Enterprise B2B Technology',
            'company_size': comp_size,
            'revenue_range': rev_range,
            'employee_count': emp_count,
            'target_account_focus': ", ".join(result.get('target_account_focus_chips') or []),
            'ideal_champion': ", ".join((result.get('target_personas') or [])[:2]),
            'tech_stack': ", ".join((result.get('tech_stack') or [])[:10]),
            'ai_confidence_score': result.get('confidence_score') or 92,
            'ai_confidence_reason': result.get('confidence_reason') or 'GTM extraction matching context.'
        }
        
        default_personas = ["Chief Revenue Officer (CRO)", "VP of Sales", "Chief Technology Officer (CTO)", "Head of Sales Operations", "VP of Marketing"]
        personas_list = result.get('target_personas') or default_personas
        if len(personas_list) < 3:
            for p in default_personas:
                if p not in personas_list:
                    personas_list.append(p)
        personas_list = personas_list[:5]
        
        personas = []
        for idx, role in enumerate(personas_list):
            personas.append({
                'role': role,
                'type': 'Economic Buyer' if idx == 0 else 'Technical Champion',
                'responsibilities': 'Managing GTM targeting campaigns.',
                'goals': 'Optimize conversion rates.',
                'roadblocks': 'Inefficient GTM search pipelines.',
                'pain_points': result.get('pain_points') or []
            })
            
        competitors = (result.get('competitors') or [])[:8]
        keywords = result.get('categorized_keywords') or {}
        buying_signals = result.get('categorized_buying_signals') or {}
        
        save_ai_pulse_insights_orm(pulse, comp_profile, personas, competitors, keywords, buying_signals)
        return
    else:
        raise ValueError("Failed to extract GTM insights: Gemini API returned an empty or invalid response.")
