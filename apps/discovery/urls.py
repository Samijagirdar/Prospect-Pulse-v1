from django.urls import path
from . import views

app_name = 'discovery'

urlpatterns = [
    path('runs/<int:run_id>/status/', views.discovery_run_status, name='discovery_run_status'),
    path('pulses/<str:pulse_uid>/results/', views.pulse_results_api, name='pulse_results_api'),
    path('pulses/<str:pulse_uid>/discovery/sources/', views.pulse_sources, name='pulse_sources'),
    path('pulses/<str:pulse_uid>/discovery/leads/', views.pulse_leads, name='pulse_leads'),
]
