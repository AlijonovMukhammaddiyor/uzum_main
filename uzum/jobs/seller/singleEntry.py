from uzum.shop.models import Shop, ShopAnalytics


def find_shop(shopId: int):
    try:
        result = Shop.objects.get(shopId=shopId)
        return result

    except Exception as _:
        return None


def create_shop(shop: dict):
    try:
        result = Shop.objects.create(**shop)
        return result

    except Exception as e:
        print("Error in createShop: ", e)
        return None


def create_shop_analytics(shop_analytics: dict):
    try:
        result = ShopAnalytics.objects.create(**shop_analytics)
        return result

    except Exception as e:
        print("Error in createShopAnalytics: ", e)
        return None
