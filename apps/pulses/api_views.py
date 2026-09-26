from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.db.models import Q

from common.auth import get_user_org
from .models import Pulse
from .serializers import ProspectPulseSerializer


class PulseListCreateAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        org = get_user_org(request)
        pulses_data = []
        if org:
            pulses = Pulse.objects.filter(organisation_id=org.id).order_by('-created_at')
            for p in pulses:
                pulses_data.append({
                    'id': p.id,
                    'name': p.name,
                    'frequency': p.frequency,
                    'frequency_display': p.get_frequency_display(),
                    'start_date': str(p.start_date),
                    'end_date': str(p.end_date) if p.end_date else None,
                    'is_active': bool(p.is_active),
                    'input_type': p.input_type,
                    'input_type_display': p.get_input_type_display(),
                    'url': p.url,
                    'text_content': p.text_content,
                    'from_document_id': p.from_document_id,
                    'created_at': p.created_at,
                    'last_processed_at': p.last_processed_at,
                    'company_size': p.company_size,
                    'revenue_range': p.revenue_range,
                    'employee_count': p.employee_count,
                    'ai_confidence_score': p.ai_confidence_score,
                    'ai_confidence_reason': p.ai_confidence_reason
                })
        return Response({'pulses': pulses_data})

    def post(self, request):
        org = get_user_org(request)
        if not org:
            return Response({'error': 'Organization not found'}, status=status.HTTP_400_BAD_REQUEST)
            
        serializer = ProspectPulseSerializer(data=request.data)
        if serializer.is_valid():
            p = serializer.save(organisation_id=org.id)
            return Response({'success': True, 'id': p.id})
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


def get_pulse_by_pk_or_uid(pk_or_uid, org_id):
    query = Q(uid=pk_or_uid)
    if str(pk_or_uid).isdigit():
        query |= Q(id=int(pk_or_uid))
    try:
        return Pulse.objects.get(query, organisation_id=org_id)
    except Pulse.DoesNotExist:
        return None


class PulseDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        org = get_user_org(request)
        pulse = get_pulse_by_pk_or_uid(pk, org.id)
        if not pulse:
            return Response({'error': 'Pulse not found'}, status=status.HTTP_404_NOT_FOUND)
            
        pulse_data_out = {
            'id': pulse.id,
            'name': pulse.name,
            'frequency': pulse.frequency,
            'frequency_display': pulse.get_frequency_display(),
            'start_date': str(pulse.start_date),
            'end_date': str(pulse.end_date) if pulse.end_date else None,
            'input_type': pulse.input_type,
            'input_type_display': pulse.get_input_type_display(),
            'url': pulse.url,
            'text_content': pulse.text_content,
            'from_document_id': pulse.from_document_id,
            'is_active': bool(pulse.is_active),
            'created_at': pulse.created_at,
            'last_processed_at': pulse.last_processed_at,
            'company_size': pulse.company_size,
            'revenue_range': pulse.revenue_range,
            'employee_count': pulse.employee_count,
            'ai_confidence_score': pulse.ai_confidence_score,
            'ai_confidence_reason': pulse.ai_confidence_reason,
            'target_account_focus_chips': pulse.target_account_focus_list,
            'competitors': pulse.competitors_list,
            'personas': pulse.personas_list,
            'categorized_keywords': pulse.categorized_keywords,
            'categorized_buying_signals': pulse.categorized_buying_signals,
            'competitors_text': ", ".join(pulse.competitors_list)
        }
        return Response({'pulse': pulse_data_out, 'feeds': []})


class PulseDeleteAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, pk):
        org = get_user_org(request)
        pulse = get_pulse_by_pk_or_uid(pk, org.id)
        if pulse:
            pulse.delete()
            return Response({'success': True})
        return Response({'success': False, 'error': 'Pulse not found'}, status=status.HTTP_404_NOT_FOUND)


class PulseToggleAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, pk):
        org = get_user_org(request)
        pulse = get_pulse_by_pk_or_uid(pk, org.id)
        if pulse:
            pulse.is_active = not pulse.is_active
            pulse.save()
            return Response({'success': True, 'is_active': pulse.is_active})
        return Response({'success': False, 'error': 'Pulse not found'}, status=status.HTTP_404_NOT_FOUND)

