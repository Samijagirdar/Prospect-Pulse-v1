from rest_framework import serializers
from .models import Pulse
from .services import pulse_service

class ProspectPulseSerializer(serializers.ModelSerializer):
    competitors = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    frequency_display = serializers.CharField(source='get_frequency_display', read_only=True)
    input_type_display = serializers.CharField(source='get_input_type_display', read_only=True)

    class Meta:
        model = Pulse
        fields = [
            'id', 'uid', 'name', 'frequency', 'frequency_display',
            'start_date', 'end_date', 'is_active', 'input_type', 'input_type_display',
            'pdf_file', 'url', 'text_content', 'from_document_id', 'created_at',
            'last_processed_at', 'competitors'
        ]
        read_only_fields = ['id', 'uid', 'created_at', 'last_processed_at']

    def validate(self, attrs):
        frequency = attrs.get('frequency', 'daily')
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')

        if start_date:
            if frequency == 'weekly':
                if not end_date:
                    raise serializers.ValidationError({'end_date': 'An end date is required for weekly pulses (minimum 7 days).'})
                if (end_date - start_date).days < 7:
                    raise serializers.ValidationError({'end_date': 'Weekly pulses require an end date at least 7 days after the start date.'})
            elif frequency == 'monthly':
                if not end_date:
                    raise serializers.ValidationError({'end_date': 'An end date is required for monthly pulses (minimum 30 days).'})
                if (end_date - start_date).days < 30:
                    raise serializers.ValidationError({'end_date': 'Monthly pulses require an end date at least 30 days after the start date.'})
            elif end_date and end_date < start_date:
                raise serializers.ValidationError({'end_date': 'End date cannot be before start date.'})

        return attrs

    def create(self, validated_data):
        org_id = validated_data.get('organisation_id')
        competitors = validated_data.get('competitors') or ''
        
        pulse_id = pulse_service.create_pulse_config(
            org_id=org_id,
            name=validated_data.get('name'),
            frequency=validated_data.get('frequency', 'daily'),
            start_date=validated_data.get('start_date'),
            end_date=validated_data.get('end_date'),
            input_type=validated_data.get('input_type', 'text'),
            pdf_file=validated_data.get('pdf_file', ''),
            url=validated_data.get('url', ''),
            text_content=validated_data.get('text_content', ''),
            from_document_id=validated_data.get('from_document_id'),
            competitors=competitors
        )
        return Pulse.objects.get(id=pulse_id)


class PulseFeedSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    pulse_id = serializers.IntegerField()
    title = serializers.CharField(max_length=500)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    source_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    company_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    status = serializers.CharField(max_length=20, default='potential')
    published_date = serializers.DateTimeField(read_only=True)
    is_enabled = serializers.BooleanField(default=True)
    confidence_score = serializers.IntegerField(default=70)
    relevance_explanation = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    first_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    last_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class DocumentSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField()
