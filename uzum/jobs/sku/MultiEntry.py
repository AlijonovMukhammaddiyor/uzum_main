from uzum.sku.models import Sku, SkuAnalytics


def create_skus_bulk(sku_list):
    try:
        print("createSkusBulk started...")

        result = Sku.objects.bulk_create(sku_list, ignore_conflicts=True)
        print(f"createSkusBulk: {len(result)} objects inserted, {len(sku_list) - len(result)} objects skipped")
        return result

    except Exception as e:
        print("Error in createSkusBulk: ", e)
        return None


def create_sku_analytics_bulk(sku_analytics_list):
    try:
        result = SkuAnalytics.objects.bulk_create(sku_analytics_list, ignore_conflicts=True)
        print(
            f"createSkuAnalyticsBulk: {len(result)} objects inserted, {len(sku_analytics_list) - len(result)} objects skipped"
        )
        return result

    except Exception as e:
        print("Error in createSkuAnalyticsBulk: ", e)
        return None
