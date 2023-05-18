from uzum.badge.models import Badge


def create_badge(badge: dict):
    try:
        result = Badge.objects.create(**badge)
        return result

    except Exception as e:
        print(f"Error in createBadge: {e}")
        return None
