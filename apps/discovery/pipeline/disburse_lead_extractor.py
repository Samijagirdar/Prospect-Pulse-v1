import logging
from apps.discovery.models import Article, Company, Competitor, Lead
from .disburse_client import DisburseClient

logger = logging.getLogger(__name__)

def extract_pulse_leads_disburse(pulse, discovery_run=None, articles_qs=None):
    """
    Extracts high-intent decision maker leads with verified contact details (emails & phones)
    via Disburse.dev for target companies identified in the discovery run.
    """
    client = DisburseClient()
    if not client.is_configured:
        print("[Disburse] DISBURSE_API_KEY not configured. Disburse lead search is paused/ready for key.")
        return 0

    # Fetch pulse target personas
    personas_list = [p.role for p in pulse.personas_rel.all()] if hasattr(pulse, 'personas_rel') else []
    target_geography = (getattr(pulse, 'target_geography', None) or "").strip()

    # Find target companies associated with this discovery run (or recent articles)
    if discovery_run:
        companies = Company.objects.filter(discovery_run=discovery_run)
    else:
        companies = Company.objects.filter(pulse=pulse).order_by('-extracted_at')[:15]

    if not companies.exists():
        print(f"[Disburse] No target companies found for pulse '{pulse.name}' to query leads for.")
        return 0

    print(f"[Disburse] Processing {companies.count()} target accounts for pulse: {pulse.name}")

    # Gather known competitors to avoid extracting competitor employees
    db_competitors = {comp.name.strip().lower() for comp in Competitor.objects.filter(pulse=pulse)}

    extracted_leads_count = 0
    seen_contacts = set()

    for company in companies:
        comp_name = company.name.strip()
        if comp_name.lower() in db_competitors:
            print(f"[Disburse] Skipping company '{comp_name}' because it is in the competitor list.")
            continue

        try:
            results = client.search_leads_for_company(
                company_name=comp_name,
                personas=personas_list,
                country=target_geography,
                limit=3
            )
        except Exception as e:
            logger.error(f"[Disburse] Error searching leads for {comp_name}: {e}")
            continue

        source_art = getattr(company, 'source_article', None)
        if not source_art:
            source_art = Article.objects.filter(pulse=pulse, is_relevant=True).first()

        for item in results:
            name = (item.get("name") or "").strip()
            title = (item.get("title") or item.get("headline") or "").strip()
            org = (item.get("company_name") or item.get("company_display_name") or comp_name).strip()
            email = (item.get("email") or "").strip() or None
            phone = (item.get("direct_phone") or item.get("cellphone") or item.get("phone") or item.get("company_phone") or "").strip() or None
            linkedin = (item.get("linkedin_url") or "").strip()

            if not name:
                continue

            dedup_key = (name.lower(), org.lower())
            if dedup_key in seen_contacts:
                continue
            seen_contacts.add(dedup_key)

            # Check DB duplicate
            if Lead.objects.filter(pulse=pulse, name__iexact=name, organization_name__iexact=org).exists():
                continue

            lead_reason = f"Verified executive at {org} via Disburse (Matched Personas: {', '.join(personas_list) if personas_list else 'Leadership'})"
            if linkedin:
                lead_reason += f" | LinkedIn: {linkedin}"

            try:
                Lead.objects.create(
                    pulse=pulse,
                    discovery_run=discovery_run,
                    source_article=source_art,
                    name=name,
                    designation=title,
                    organization_name=org,
                    score=company.score or 80,
                    buying_signal=company.buying_signal or "Target Account Decision Maker",
                    reason=lead_reason,
                    email=email,
                    phone=phone,
                    linkedin_url=linkedin or None
                )


                extracted_leads_count += 1
                contact_info = []
                if email: contact_info.append(f"email: {email}")
                if phone: contact_info.append(f"phone: {phone}")
                info_str = f" ({', '.join(contact_info)})" if contact_info else " (no contact details)"
                print(f"  [Disburse Lead] Created: {name} - {title} at {org}{info_str}")
            except Exception as le_err:
                logger.error(f"[Disburse] Error creating lead {name}: {le_err}")

    print(f"[Disburse] Completed lead discovery. Total new leads extracted: {extracted_leads_count}")
    return extracted_leads_count
