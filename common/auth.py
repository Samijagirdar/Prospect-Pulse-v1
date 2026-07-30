import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def get_user_org(request):
    """
    Reads the organization/tenant context injected by the parent app.
    Checks request.organization first (set by parent app's middleware),
    falling back to request.user.profile.organization if that's how
    the parent app links users to orgs instead.
    """
    org = getattr(request, 'organization', None)

    if not org and getattr(request.user, 'is_authenticated', False):
        profile = getattr(request.user, 'profile', None)
        if profile:
            org = getattr(profile, 'organization', None)

    if not org:
        if settings.DEBUG:
            logger.warning(
                "No organization context found on request — using dev "
                "MockOrg fallback. This must never happen outside DEBUG."
            )
            org = _MockOrg()
        else:
            raise RuntimeError(
                "No organization context on request and DEBUG is False. "
                "The parent app must inject request.organization "
                "(or request.user.profile.organization) before this "
                "view runs."
            )

    return org


class _MockOrg:
    """Dev-only stand-in so this project can run standalone before the
    parent app wires in real tenant context. Never used outside DEBUG."""
    id = 1
    name = "Mock Organisation"


def ensure_authenticated_dev(request):
    """
    Dev convenience: auto-logs-in the first available user for
    unauthenticated browser sessions so you can click through the UI
    without building a login flow. Hard-gated to DEBUG — must never
    run in production.
    """
    if not settings.DEBUG:
        return

    if request.user.is_authenticated:
        return

    from django.contrib.auth import login
    from django.contrib.auth.models import User

    user = User.objects.first()

    if not user:
        user = User.objects.create_superuser(
            username='devadmin',
            email='devadmin@example.com',
            password='password',
        )
        logger.warning(
            "Created dev superuser 'devadmin' with a default password. "
            "DEBUG-only — this must never run in production."
        )

    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)
    request.user = user