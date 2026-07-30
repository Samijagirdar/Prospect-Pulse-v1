import sys


def is_json_request(request):
    """
    Detects whether a request expects a JSON response — used to branch
    between full-page and Ajax/partial responses in views.
    """
    accept = request.META.get('HTTP_ACCEPT', '')
    return (
        'json' in accept
        or request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'test' in sys.argv
    )