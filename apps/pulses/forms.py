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
            'name', 'frequency', 'custom_days', 'start_date', 'end_date',
            'input_type', 'pdf_file', 'url', 'text_content'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Enterprise SaaS Discovery'}),
            'frequency': forms.Select(attrs={'class': 'form-select'}),
            'custom_days': forms.NumberInput(attrs={'class': 'form-control', 'id': 'custom_days', 'min': 1}),
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
        self.fields['from_document'].choices = choices
        
        # Populate from_document if editing an existing instance
        if self.instance and self.instance.pk and self.instance.from_document_id:
            self.fields['from_document'].initial = self.instance.from_document_id

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        input_type = cleaned_data.get('input_type')
        frequency = cleaned_data.get('frequency')
        custom_days = cleaned_data.get('custom_days')
        
        # Enforce name is compulsory
        if not name:
            self.add_error('name', 'The name field is compulsory.')
            
        # Validation for Custom Days when frequency is custom
        if frequency == 'custom' and not custom_days:
            self.add_error('custom_days', 'Custom days must be specified for Custom frequency.')

        # Enforce that exactly one matching field is filled, and clear the other sources
        if input_type == 'pdf':
            if not cleaned_data.get('pdf_file'):
                self.add_error('pdf_file', 'A PDF file must be uploaded for PDF input type.')
            cleaned_data['url'] = None
            cleaned_data['text_content'] = ''
            cleaned_data['from_document'] = None
            
        elif input_type == 'url':
            if not cleaned_data.get('url'):
                self.add_error('url', 'A URL must be provided for URL input type.')
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
