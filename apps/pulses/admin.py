from django.contrib import admin
from .models import Pulse, CompanyProfile, Persona, TargetCompetitor, Keyword, BuyingSignal

@admin.register(Pulse)
class PulseAdmin(admin.ModelAdmin):
    list_display = ('name', 'uid', 'organisation_id', 'frequency', 'is_active', 'created_at')
    search_fields = ('name', 'uid')
    list_filter = ('is_active', 'frequency')

@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ('pulse', 'industry', 'company_size', 'revenue_range', 'ai_confidence_score')
    search_fields = ('pulse__name', 'industry')

@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ('role', 'type', 'pulse')
    search_fields = ('role', 'pulse__name')

@admin.register(TargetCompetitor)
class TargetCompetitorAdmin(admin.ModelAdmin):
    list_display = ('competitor_name', 'pulse')
    search_fields = ('competitor_name', 'pulse__name')

@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'category', 'pulse')
    search_fields = ('keyword', 'pulse__name')

@admin.register(BuyingSignal)
class BuyingSignalAdmin(admin.ModelAdmin):
    list_display = ('signal_name', 'category', 'pulse')
    search_fields = ('signal_name', 'pulse__name')
