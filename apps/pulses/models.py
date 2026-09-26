from django.db import models

class Pulse(models.Model):
    """
    Campaign configuration settings for a Prospect Pulse scanning run.
    """
    INPUT_TYPE_CHOICES = [
        ('pdf', 'PDF File'),
        ('url', 'Web URL'),
        ('text', 'Manual Text'),
        ('icp', 'Existing ICP')
    ]
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly')
    ]
    LOOKBACK_CHOICES = [
        ('30d', 'Last 1 Month (30 Days)'),
        ('60d', 'Last 2 Months (60 Days)'),
        ('90d', 'Last 3 Months (90 Days)'),
        ('180d', 'Last 6 Months (180 Days)'),
        ('365d', 'Last 1 Year (365 Days)'),
    ]

    uid = models.CharField(max_length=50, unique=True, db_index=True)
    organisation_id = models.IntegerField()
    name = models.CharField(max_length=255)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='daily')
    historical_lookback = models.CharField(max_length=10, choices=LOOKBACK_CHOICES, default='60d')
    target_geography = models.TextField(null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    input_type = models.CharField(max_length=20, choices=INPUT_TYPE_CHOICES, default='text')
    pdf_file = models.CharField(max_length=255, null=True, blank=True)
    url = models.TextField(null=True, blank=True)
    text_content = models.TextField(null=True, blank=True)
    from_document_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

    @property
    def is_expired(self):
        from django.utils import timezone
        if self.end_date and self.end_date < timezone.now().date():
            return True
        return False

    @property
    def target_geography_list(self):
        if not self.target_geography:
            return []
        return [g.strip() for g in self.target_geography.split(',') if g.strip()]

    @property
    def competitors_list(self):
        return [c.competitor_name for c in self.competitors.all()]

    @property
    def target_account_focus_list(self):
        try:
            focus = self.company_profile.target_account_focus
            if not focus:
                return []
            return [f.strip() for f in focus.split(',') if f.strip()]
        except CompanyProfile.DoesNotExist:
            return []

    def _get_profile_field(self, field_name, default=""):
        try:
            profile = self.company_profile
            val = getattr(profile, field_name, None)
            return val if val is not None else default
        except CompanyProfile.DoesNotExist:
            return default

    @property
    def company_size(self):
        return self._get_profile_field('company_size', '100-500')

    @property
    def revenue_range(self):
        return self._get_profile_field('revenue_range', '$10M - $50M')

    @property
    def employee_count(self):
        return self._get_profile_field('employee_count', '100-400')

    @property
    def ai_confidence_score(self):
        return self._get_profile_field('ai_confidence_score', 90)

    @property
    def ai_confidence_reason(self):
        return self._get_profile_field('ai_confidence_reason', '')

    @property
    def total_prompt_tokens(self):
        from django.db.models import Sum
        res = self.discovery_runs.aggregate(s=Sum('prompt_tokens'))['s']
        return res if res else 0

    @property
    def total_completion_tokens(self):
        from django.db.models import Sum
        res = self.discovery_runs.aggregate(s=Sum('completion_tokens'))['s']
        return res if res else 0

    @property
    def total_tokens_consumed(self):
        from django.db.models import Sum
        res = self.discovery_runs.aggregate(s=Sum('total_tokens'))['s']
        return res if res else (self.total_prompt_tokens + self.total_completion_tokens)

    @property
    def estimated_total_cost(self):
        p_tokens = self.total_prompt_tokens
        c_tokens = self.total_completion_tokens
        return (p_tokens * 0.000000075) + (c_tokens * 0.00000030)

    @property
    def personas_list(self):
        res = []
        for p in self.personas_rel.all():
            pps = p.pain_points or ''
            pain_points_list = [pt.strip() for pt in pps.split(',') if pt.strip()]
            res.append({
                'role': p.role,
                'type': p.type,
                'responsibilities': p.responsibilities,
                'goals': p.goals,
                'roadblocks': p.roadblocks,
                'pain_points': pain_points_list
            })
        return res

    @property
    def categorized_keywords(self):
        res = {}
        for kw in self.keywords_rel.all():
            cat = kw.category
            if cat not in res:
                res[cat] = []
            res[cat].append(kw.keyword)
        if not res:
            return {
                "Primary Discovery": ["Revenue Intelligence Platform", "Sales Engagement Software", "AI Sales Automation"],
                "Secondary Discovery": ["Enterprise Prospecting", "CRM Data Enrichment", "Outbound Sales Platform"]
            }
        return res

    @property
    def categorized_buying_signals(self):
        res = {}
        for sig in self.buying_signals_rel.all():
            cat = sig.category
            if cat not in res:
                res[cat] = []
            res[cat].append(sig.signal_name)
        if not res:
            return {
                "Organizational": ["Leadership Changes", "Office Expansion", "Product Launch"],
                "Technology": ["Technology Adoption", "CRM Migration"],
                "Business": ["Hiring SDRs", "Series A Funding", "Series B Funding"]
            }
        return res

    @property
    def keywords(self):
        flat = []
        for cat, items in self.categorized_keywords.items():
            flat.extend(items)
        return ", ".join(flat)

    @property
    def buying_signals(self):
        flat = []
        for cat, items in self.categorized_buying_signals.items():
            flat.extend(items)
        return ", ".join(flat)


class CompanyProfile(models.Model):
    """
    Target account details parsed by Gemini (Ideal Customer Profile).
    """
    pulse = models.OneToOneField(Pulse, on_delete=models.CASCADE, related_name='company_profile')
    industry = models.CharField(max_length=150, null=True, blank=True)
    company_size = models.CharField(max_length=100, null=True, blank=True)
    revenue_range = models.CharField(max_length=100, null=True, blank=True)
    employee_count = models.CharField(max_length=100, null=True, blank=True)
    target_account_focus = models.TextField(null=True, blank=True)  # Comma-separated focus chips
    ideal_champion = models.TextField(null=True, blank=True)
    tech_stack = models.TextField(null=True, blank=True)
    ai_confidence_score = models.IntegerField(default=90)
    ai_confidence_reason = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"ICP for {self.pulse.name}"


class Persona(models.Model):
    """
    Target buyer roles and executive profiles for target accounts.
    """
    pulse = models.ForeignKey(Pulse, on_delete=models.CASCADE, related_name='personas_rel')
    role = models.CharField(max_length=255)
    type = models.CharField(max_length=100, null=True, blank=True)
    responsibilities = models.TextField(null=True, blank=True)
    goals = models.TextField(null=True, blank=True)
    roadblocks = models.TextField(null=True, blank=True)
    pain_points = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.role} ({self.pulse.name})"


class TargetCompetitor(models.Model):
    """
    Competitor brands monitored by the campaign.
    """
    pulse = models.ForeignKey(Pulse, on_delete=models.CASCADE, related_name='competitors')
    competitor_name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.competitor_name} (Competitor of {self.pulse.name})"


class Keyword(models.Model):
    """
    Keywords parsed/generated to be used by discovery crawlers.
    """
    pulse = models.ForeignKey(Pulse, on_delete=models.CASCADE, related_name='keywords_rel')
    keyword = models.CharField(max_length=255)
    category = models.CharField(max_length=100)  # Primary or Secondary Discovery

    def __str__(self):
        return f"{self.keyword} ({self.category})"


class BuyingSignal(models.Model):
    """
    Triggers/buying signals (Organizational, Tech, Business) monitored by the campaign.
    """
    pulse = models.ForeignKey(Pulse, on_delete=models.CASCADE, related_name='buying_signals_rel')
    signal_name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)  # Organizational, Technology, Business

    def __str__(self):
        return f"{self.signal_name} ({self.category})"


