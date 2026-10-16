from monitoring.models import Alert


def admin_header_context(request):
    """
    Supplies global notifications and system alert status to base_admin.html.
    Uses lightweight indexed queries to avoid any performance penalty.
    """
    if not request.user.is_authenticated:
        return {}

    try:
        open_alerts = list(
            Alert.objects.filter(resolved_at__isnull=True)
            .select_related('kiosk', 'kiosk__store')
            .order_by('-opened_at')[:8]
        )
        open_alerts_count = Alert.objects.filter(resolved_at__isnull=True).count()
    except Exception:
        open_alerts = []
        open_alerts_count = 0

    return {
        'top_alerts': open_alerts,
        'top_alerts_count': open_alerts_count,
    }
