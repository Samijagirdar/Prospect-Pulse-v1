from .models import Notification

def notifications_context(request):
    """
    Injects notifications globally into all template contexts.
    """
    if request.user.is_authenticated:
        # Get the top 10 recent notifications
        notifications = Notification.objects.all()[:10]
        unread_count = Notification.objects.filter(is_read=False).count()
    else:
        notifications = []
        unread_count = 0
        
    return {
        'global_notifications': notifications,
        'unread_notifications_count': unread_count
    }
