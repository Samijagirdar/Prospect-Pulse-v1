from django.db import models
from apps.pulses.models import Pulse

class DiscoveryRun(models.Model):
    """
    Tracks each execution of the scraping/discovery pipeline.
    """
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    pulse = models.ForeignKey(Pulse, on_delete=models.CASCADE, related_name='discovery_runs')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    articles_scraped = models.IntegerField(default=0)
    articles_relevant = models.IntegerField(default=0)
    leads_extracted = models.IntegerField(default=0)
    error_message = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Run #{self.id} for {self.pulse.name} ({self.status})"


class Article(models.Model):
    """
    Stores scraped news documents, embeddings, and relevance evaluations.
    """
    pulse = models.ForeignKey(Pulse, on_delete=models.CASCADE, related_name='scraped_articles')
    discovery_run = models.ForeignKey(DiscoveryRun, on_delete=models.CASCADE, related_name='scraped_articles', null=True, blank=True)
    title = models.CharField(max_length=500)
    source = models.CharField(max_length=255)
    url = models.TextField()
    publication_date = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    scraped_at = models.DateTimeField(auto_now_add=True)
    embedding = models.BinaryField(null=True, blank=True)  # Cosine similarity vector representation
    is_duplicate = models.BooleanField(default=False)
    matched_original = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='duplicates')
    duplicate_reason = models.TextField(null=True, blank=True)
    delta_summary = models.TextField(null=True, blank=True)
    is_relevant = models.BooleanField(default=False)
    relevance_score = models.IntegerField(default=0)
    buying_signal = models.CharField(max_length=255, null=True, blank=True)
    relevance_tier = models.CharField(max_length=50, null=True, blank=True)
    relevance_reason = models.TextField(null=True, blank=True)
    executive_summary = models.TextField(null=True, blank=True)
    is_summarized = models.BooleanField(default=False)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)

    def __str__(self):
        return self.title


class Company(models.Model):
    """
    Target companies extracted from scraped relevant articles.
    """
    pulse = models.ForeignKey(Pulse, on_delete=models.CASCADE, related_name='extracted_companies')
    discovery_run = models.ForeignKey(DiscoveryRun, on_delete=models.CASCADE, related_name='extracted_companies', null=True, blank=True)
    source_article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='extracted_companies')
    name = models.CharField(max_length=255, db_index=True)
    score = models.IntegerField(default=0)
    buying_signal = models.CharField(max_length=255, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    extracted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.pulse.name})"


class Lead(models.Model):
    """
    Contact leads extracted from scraped relevant articles.
    """
    pulse = models.ForeignKey(Pulse, on_delete=models.CASCADE, related_name='extracted_leads')
    discovery_run = models.ForeignKey(DiscoveryRun, on_delete=models.CASCADE, related_name='extracted_leads', null=True, blank=True)
    source_article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='extracted_leads')
    name = models.CharField(max_length=255)
    designation = models.CharField(max_length=255, null=True, blank=True)
    organization_name = models.CharField(max_length=255, null=True, blank=True)
    score = models.IntegerField(default=0)
    buying_signal = models.CharField(max_length=255, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    email = models.EmailField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    extracted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.organization_name})"


class Competitor(models.Model):
    """
    Competitor brands extracted/mentioned in scraped relevant articles.
    """
    pulse = models.ForeignKey(Pulse, on_delete=models.CASCADE, related_name='extracted_competitors')
    discovery_run = models.ForeignKey(DiscoveryRun, on_delete=models.CASCADE, related_name='extracted_competitors', null=True, blank=True)
    source_article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='extracted_competitors')
    name = models.CharField(max_length=255)
    buying_signal = models.CharField(max_length=255, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    extracted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} (Mentioned in {self.pulse.name})"


class Correction(models.Model):
    """
    Audit log of manual corrections to article relevance tags.
    """
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='corrections')
    original_tier = models.CharField(max_length=50)
    corrected_tier = models.CharField(max_length=50)
    note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Correction for Article #{self.article.id}"


class Notification(models.Model):
    """
    Stores system notifications for campaign/discovery status updates.
    """
    title = models.CharField(max_length=255)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
