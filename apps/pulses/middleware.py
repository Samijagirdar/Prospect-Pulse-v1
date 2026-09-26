import logging
import traceback
from django.http import JsonResponse
from django.shortcuts import redirect
from django.contrib import messages
from django.conf import settings

logger = logging.getLogger('django.request')

class GlobalExceptionHandlingMiddleware:
    """
    Middleware to catch all exceptions globally.
    - In Development (DEBUG=True), lets general exceptions through to django debug page
      but catches Gemini/Quota errors cleanly.
    - In Production (DEBUG=False), catches all exceptions.
    - AJAX/API requests get clean JsonResponse {"success": False, "error": "..."} with status 500.
    - HTML page loads get redirected back to their previous page with a warning flash message.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        msg = str(exception)
        is_gemini_error = False
        error_msg = ""

        # 1. Identify specific Gemini API/quota/authorization limits
        if any(keyword in msg for keyword in ["PERMISSION_DENIED", "CONSUMER_SUSPENDED", "403", "401", "UNAUTHENTICATED", "ACCESS_TOKEN_TYPE_UNSUPPORTED"]):
            is_gemini_error = True
            error_msg = "API Error please contact your administrator"
        elif any(keyword in msg for keyword in ["RESOURCE_EXHAUSTED", "quota", "spending cap", "429"]):
            is_gemini_error = True
            error_msg = "You have exceeded your monthly quota"
        elif "Empty response text from LLM" in msg:
            is_gemini_error = True
            error_msg = "Failed to run discovery: Gemini API returned an empty response. Please verify your connection or try again."
        elif "Unable to parse valid JSON from LLM" in msg:
            is_gemini_error = True
            error_msg = "Failed to run discovery: AI returned an invalid response format."
        elif "Failed to extract GTM insights" in msg:
            is_gemini_error = True
            if any(keyword in msg for keyword in ["PERMISSION_DENIED", "CONSUMER_SUSPENDED", "403", "401", "UNAUTHENTICATED"]):
                error_msg = "API Error please contact your administrator"
            else:
                import re
                clean_text = re.sub(r'api_key[=:][A-Za-z0-9_\-]+', 'api_key=***HIDDEN***', msg)
                error_msg = f"Failed to extract GTM insights: {clean_text}"

        # 2. Always log the error details on the backend (Console / Logs)
        user_str = getattr(request, 'user', 'AnonymousUser')
        logger.error(
            f"Exception in request: {request.method} {request.path} (User: {user_str})\n"
            f"Details: {msg}\n"
            f"{traceback.format_exc()}"
        )

        # 3. Determine if we should handle this exception
        # Gemini errors are handled in all environments.
        # General system errors are only handled globally when DEBUG is False (Production).
        should_handle = is_gemini_error or (not settings.DEBUG)

        if not should_handle:
            # Let Django's default traceback handle it in development
            return None

        # Set fallback error message for general exceptions
        if not error_msg:
            error_msg = "Something went wrong on our end. Our engineering team has been notified. Please try again later."

        # 4. Check if request expects JSON (AJAX/API check)
        is_json_request = (
            request.headers.get('x-requested-with') == 'XMLHttpRequest' or
            'application/json' in request.headers.get('accept', '').lower() or
            request.content_type == 'application/json' or
            any(request.path.startswith(prefix) for prefix in ['/runs/', '/articles/', '/api/'])
        )

        if is_json_request:
            status_code = 403 if error_msg == "API Error please contact your administrator" else 500
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=status_code)

        # 5. Handle standard HTML requests (Redirect with message)
        messages.error(request, error_msg)
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        return redirect('prospect_pulse:prospect_pulse_list')


class PulseExistenceMiddleware:
    """
    Middleware to verify that the pulse ID requested in any /pulses/<id>/ URL path
    actually exists in the database. If not, it logs a backend error,
    adds a warning message, and redirects to the main dashboard.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path.strip('/')
        segments = [s for s in path.split('/') if s]
        
        if len(segments) >= 2 and segments[0] == 'pulses':
            pulse_id = segments[1]
            # Exclude non-pulse-id endpoints
            if pulse_id not in ['create', 'documents', 'admin']:
                from apps.pulses.models import Pulse
                pulse_exists = False
                try:
                    # Check if ID is numeric or string UID
                    if str(pulse_id).isdigit():
                        pulse_exists = Pulse.objects.filter(id=int(pulse_id)).exists()
                    else:
                        pulse_exists = Pulse.objects.filter(uid=pulse_id).exists()
                except Exception:
                    pass
                
                if not pulse_exists:
                    # Log backend error
                    logger.error(f"Backend error: Pulse with ID '{pulse_id}' does not exist (Request: {request.method} {request.path})")
                    # Add error message
                    messages.error(request, "Wrong ID or no pulse with this ID.")
                    # Redirect to dashboard
                    return redirect('prospect_pulse:prospect_pulse_list')

        return self.get_response(request)

