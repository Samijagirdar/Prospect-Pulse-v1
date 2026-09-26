import uuid
from ..models import Pulse, CompanyProfile, TargetCompetitor
from .ai import enrichment_service

def create_pulse_config(org_id, name, frequency, start_date, end_date, input_type, pdf_file, url, text_content, from_document_id, competitors, historical_lookback='60d', target_geography=None):
    # Generate secure unique identifier
    uid = str(uuid.uuid4().hex[:12])
    
    pulse = Pulse.objects.create(
        organisation_id=org_id,
        uid=uid,
        name=name,
        frequency=frequency,
        historical_lookback=historical_lookback,
        target_geography=target_geography,
        start_date=start_date,
        end_date=end_date,
        input_type=input_type,
        pdf_file=pdf_file,
        url=url,
        text_content=text_content,
        from_document_id=from_document_id
    )
    
    # Create empty CompanyProfile
    CompanyProfile.objects.create(pulse=pulse)
    
    # Trigger Gemini AI profile insights generation (synchronous for v1)
    enrichment_service.generate_ai_pulse_insights(pulse)
    
    # Create target competitors
    if competitors:
        comps = [c.strip() for c in competitors.split(',') if c.strip()]
        for comp in comps:
            TargetCompetitor.objects.create(pulse=pulse, competitor_name=comp)
            
    return pulse.id


def update_pulse_config(pulse_id, name, frequency, start_date, end_date, input_type, pdf_file, url, text_content, from_document_id, competitors, historical_lookback='60d', target_geography=None):
    Pulse.objects.filter(id=pulse_id).update(
        name=name,
        frequency=frequency,
        historical_lookback=historical_lookback,
        target_geography=target_geography,
        start_date=start_date,
        end_date=end_date,
        input_type=input_type,
        pdf_file=pdf_file,
        url=url,
        text_content=text_content,
        from_document_id=from_document_id
    )
    
    pulse = Pulse.objects.get(id=pulse_id)
    pulse.competitors.all().delete()
    if competitors:
        comps = [c.strip() for c in competitors.split(',') if c.strip()]
        for comp in comps:
            TargetCompetitor.objects.create(pulse=pulse, competitor_name=comp)
