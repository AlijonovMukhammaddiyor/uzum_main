from uzum.shop.models import ShopAnalytics


def create_shop_analytics_bulk(analytics):
    try:
        result = ShopAnalytics.objects.bulk_create(analytics, ignore_conflicts=True)
        print(
            f"createShopAnalyticsBulk: {len(result)} objects inserted, {len(analytics) - len(result)} objects skipped"
        )
        return result

    except Exception as e:
        print("Error in createShopAnalyticsBulk: ", e)
        return None
