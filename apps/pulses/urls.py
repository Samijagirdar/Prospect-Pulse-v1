from django.urls import path
from . import views

app_name = 'prospect_pulse'

urlpatterns = [
    # Pulse Management Routes
    path('', views.pulse_list, name='prospect_pulse_list'),
    path('create/', views.pulse_create, name='prospect_pulse_create'),
    path('<str:pk>/details/', views.pulse_detail, name='prospect_pulse_detail'),
    path('<str:pk>/edit/', views.pulse_edit, name='prospect_pulse_edit'),
    path('<str:pk>/delete/', views.pulse_delete, name='prospect_pulse_delete'),
    path('<str:pk>/toggle/', views.pulse_toggle, name='prospect_pulse_toggle'),
    path('<str:pk>/discover/', views.pulse_discover, name='prospect_pulse_discover'),
    path('<str:pk>/manage-item/', views.pulse_manage_item, name='pulse_manage_item'),
]
