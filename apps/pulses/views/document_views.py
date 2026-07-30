from django.shortcuts import get_object_or_404
from django.http import JsonResponse

from common.auth import get_user_org
from common.utils import is_json_request

def document_list(request):
    from .. import api_views
    return api_views.DocumentListAPIView.as_view()(request)


def extract_profile(request, doc_id):
    return JsonResponse({'profile_text': ''})
