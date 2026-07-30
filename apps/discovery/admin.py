from django.contrib import admin
from .models import DiscoveryRun, Article, Company, Lead, Competitor, Correction

@admin.register(DiscoveryRun)
class DiscoveryRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'pulse', 'status', 'started_at', 'completed_at', 'articles_scraped', 'articles_relevant')
    list_filter = ('status', 'started_at')
    search_fields = ('pulse__name',)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'pulse', 'is_duplicate', 'is_relevant', 'relevance_tier', 'scraped_at')
    list_filter = ('is_duplicate', 'is_relevant', 'relevance_tier', 'scraped_at')
    search_fields = ('title', 'source', 'pulse__name')


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'pulse', 'score', 'buying_signal', 'extracted_at')
    list_filter = ('extracted_at', 'score')
    search_fields = ('name', 'pulse__name')


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'designation', 'organization_name', 'pulse', 'score', 'extracted_at')
    list_filter = ('extracted_at', 'score')
    search_fields = ('name', 'organization_name', 'pulse__name')


@admin.register(Competitor)
class CompetitorAdmin(admin.ModelAdmin):
    list_display = ('name', 'pulse', 'buying_signal', 'extracted_at')
    list_filter = ('extracted_at',)
    search_fields = ('name', 'pulse__name')


@admin.register(Correction)
class CorrectionAdmin(admin.ModelAdmin):
    list_display = ('article', 'original_tier', 'corrected_tier', 'created_at')
    list_filter = ('created_at',)
