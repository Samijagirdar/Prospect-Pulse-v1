from django import forms
from .models import Pulse

class ProspectPulseForm(forms.ModelForm):
    # Non-model fields that require custom handling during saving
    competitors = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. CompetitorA, CompetitorB (comma-separated, optional)'})
    )
    from_document = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_from_document'})
    )

    class Meta:
        model = Pulse
        fields = [
            'name', 'frequency', 'historical_lookback', 'target_geography', 'start_date', 'end_date',
            'input_type', 'pdf_file', 'url', 'text_content'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Enterprise SaaS Discovery'}),
            'frequency': forms.Select(attrs={'class': 'form-select'}),
            'historical_lookback': forms.Select(attrs={'class': 'form-select'}),
            'target_geography': forms.TextInput(attrs={'class': 'form-control', 'id': 'target_geography', 'placeholder': 'e.g. United States, United Kingdom, Singapore, India (optional)'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'input_type': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'pdf_file': forms.FileInput(attrs={'class': 'form-control'}),
            'url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com'}),
            'text_content': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Describe your target customer profile...'}),
        }

    def __init__(self, *args, **kwargs):
        organisation = kwargs.pop('organisation', None)
        super().__init__(*args, **kwargs)
        
        choices = [('', "Select an existing proposal (ICP)...")]
        try:
            # Fetch using raw SQL cursor to avoid Django model/migration dependency
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, name FROM gtm_gtmplan ORDER BY name")
                for row in cursor.fetchall():
                    choices.append((str(row[0]), row[1]))
        except Exception:
            pass
            
        self.fields['from_document'].choices = choices
        
        # Populate from_document if editing an existing instance
        if self.instance and self.instance.pk:
            if self.instance.from_document_id:
                self.fields['from_document'].initial = str(self.instance.from_document_id)
            # In edit mode, ONLY name, end_date, competitors, and target_geography can be changed.
            # Disable all other fields:
            self.fields['start_date'].disabled = True
            self.fields['frequency'].disabled = True
            self.fields['historical_lookback'].disabled = True
            self.fields['input_type'].disabled = True
            self.fields['from_document'].disabled = True
            self.fields['pdf_file'].disabled = True
            self.fields['url'].disabled = True
            self.fields['text_content'].disabled = True

            self.fields['frequency'].widget.attrs.update({'data-locked': 'true'})
            self.fields['historical_lookback'].widget.attrs.update({'data-locked': 'true'})
            self.fields['start_date'].widget.attrs.update({'data-locked': 'true'})
            self.fields['input_type'].widget.attrs.update({'data-locked': 'true'})
            self.fields['from_document'].widget.attrs.update({'data-locked': 'true', 'style': 'cursor: not-allowed; opacity: 0.7;'})
            self.fields['pdf_file'].widget.attrs.update({'data-locked': 'true'})
            self.fields['url'].widget.attrs.update({'readonly': 'readonly', 'data-locked': 'true', 'style': 'cursor: not-allowed; opacity: 0.7;'})
            self.fields['text_content'].widget.attrs.update({'readonly': 'readonly', 'data-locked': 'true', 'style': 'cursor: not-allowed; opacity: 0.7;'})

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        input_type = cleaned_data.get('input_type')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        frequency = cleaned_data.get('frequency')
        
        # In edit mode, locked fields strictly keep their existing instance values
        if self.instance and self.instance.pk:
            start_date = self.instance.start_date
            frequency = self.instance.frequency
            input_type = self.instance.input_type
            cleaned_data['start_date'] = start_date
            cleaned_data['frequency'] = frequency
            cleaned_data['historical_lookback'] = self.instance.historical_lookback
            cleaned_data['input_type'] = input_type
            cleaned_data['pdf_file'] = self.instance.pdf_file
            cleaned_data['url'] = self.instance.url
            cleaned_data['text_content'] = self.instance.text_content
            cleaned_data['from_document'] = str(self.instance.from_document_id) if self.instance.from_document_id else None

        # Enforce name is compulsory
        if not name or not name.strip():
            self.add_error('name', 'The name field is compulsory.')

        # Date validations
        from datetime import date
        today = date.today()

        # If new pulse, start_date cannot be in the past
        if not (self.instance and self.instance.pk):
            if start_date and start_date < today:
                self.add_error('start_date', 'Start date cannot be in the past.')

        # Frequency & date duration checks
        if start_date:
            if frequency == 'weekly':
                if not end_date:
                    self.add_error('end_date', 'An end date is required for weekly pulses (minimum 7 days).')
                else:
                    diff_days = (end_date - start_date).days
                    if diff_days < 0:
                        self.add_error('end_date', 'End date cannot be before start date.')
                    elif diff_days < 7:
                        self.add_error('end_date', f'Weekly pulses require a duration of at least 7 days between start and end date (currently {diff_days} day{"s" if diff_days != 1 else ""}).')
            elif frequency == 'monthly':
                if not end_date:
                    self.add_error('end_date', 'An end date is required for monthly pulses (minimum 30 days).')
                else:
                    diff_days = (end_date - start_date).days
                    if diff_days < 0:
                        self.add_error('end_date', 'End date cannot be before start date.')
                    elif diff_days < 30:
                        self.add_error('end_date', f'Monthly pulses require a duration of at least 30 days between start and end date (currently {diff_days} day{"s" if diff_days != 1 else ""}).')
            else:
                # Daily or other
                if end_date:
                    diff_days = (end_date - start_date).days
                    if diff_days < 0:
                        self.add_error('end_date', 'End date cannot be before start date.')

        # Only validate content source on pulse creation (since it is locked in edit mode)
        if not (self.instance and self.instance.pk):
            if input_type == 'pdf':
                uploaded_file = self.files.get('pdf_file') or cleaned_data.get('pdf_file')
                if not uploaded_file:
                    self.add_error('pdf_file', 'A PDF file must be uploaded for PDF input type.')
                else:
                    filename = getattr(uploaded_file, 'name', str(uploaded_file))
                    filesize = getattr(uploaded_file, 'size', 0)
                    if not filename.lower().endswith('.pdf'):
                        self.add_error('pdf_file', 'Only PDF files (.pdf) are allowed.')
                    elif filesize > 15 * 1024 * 1024:
                        self.add_error('pdf_file', 'PDF file size exceeds maximum allowed limit (15MB).')
                cleaned_data['url'] = None
                cleaned_data['text_content'] = ''
                cleaned_data['from_document'] = None
                
            elif input_type == 'url':
                url_val = cleaned_data.get('url')
                if not url_val:
                    self.add_error('url', 'A URL must be provided for URL input type.')
                else:
                    from apps.pulses.services.ai.url_service import is_safe_public_url
                    if not is_safe_public_url(url_val):
                        self.add_error('url', 'Invalid or restricted URL. Only public, accessible HTTP/HTTPS websites are permitted.')
                cleaned_data['pdf_file'] = None
                cleaned_data['text_content'] = ''
                cleaned_data['from_document'] = None
                
            elif input_type == 'text':
                if not cleaned_data.get('text_content'):
                    self.add_error('text_content', 'Text content must be provided for Manual Text input type.')
                cleaned_data['pdf_file'] = None
                cleaned_data['url'] = None
                cleaned_data['from_document'] = None
                
            elif input_type == 'icp':
                if not cleaned_data.get('from_document'):
                    self.add_error('from_document', 'Please select an existing proposal (ICP) document.')
                cleaned_data['pdf_file'] = None
                cleaned_data['url'] = None
            
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Map manually handled form field 'from_document' to model field 'from_document_id'
        from_doc = self.cleaned_data.get('from_document')
        if from_doc:
            instance.from_document_id = int(from_doc)
        else:
            instance.from_document_id = None
            
        if commit:
            instance.save()
            
        return instance
