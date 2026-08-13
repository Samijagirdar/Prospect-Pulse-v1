from django.urls import path
from . import views

app_name = 'discovery'

urlpatterns = [
    path('runs/<int:run_id>/status/', views.discovery_run_status, name='discovery_run_status'),
    path('pulses/<str:pulse_uid>/results/', views.pulse_results_api, name='pulse_results_api'),
    path('pulses/<str:pulse_uid>/discovery/sources/', views.pulse_sources, name='pulse_sources'),
    path('pulses/<str:pulse_uid>/discovery/leads/', views.pulse_leads, name='pulse_leads'),
    path('articles/<int:article_id>/summarize/', views.pulse_article_summarize_manual, name='pulse_article_summarize_manual'),
    path('articles/<int:article_id>/move-intent/', views.move_article_to_high_intent, name='move_article_to_high_intent'),
    path('notifications/mark-read/', views.mark_notifications_read, name='mark_notifications_read'),
    path('leads/add-to-campaign/', views.add_leads_to_campaign, name='add_leads_to_campaign'),
    path('leads/enrich/', views.enrich_leads, name='enrich_leads'),
    path('leads/move-to-crm/', views.move_leads_to_crm, name='move_leads_to_crm'),
]
