from uzum.badge.models import Badge


def create_badge_instance(badge_api):
    try:
        return Badge(
            **{
                "badge_id": badge_api["id"],
                "text": badge_api["text"],
                "type": badge_api["type"],
                "link": badge_api["link"],
                "textColor": badge_api["textColor"],
                "backgroundColor": badge_api["backgroundColor"],
                "description": badge_api["description"],
            }
        )
    except Exception as e:
        print(f"Error in createBadge: {e}")
        return None
