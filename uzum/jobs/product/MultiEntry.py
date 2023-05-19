import time
import traceback

from uzum.badge.models import Badge
from uzum.category.models import Category
from uzum.jobs.campaign.main import update_or_create_campaigns
from uzum.jobs.product.utils import prepareProductData
from uzum.jobs.seller.MultiEntry import create_shop_analytics_bulk
from uzum.jobs.sku.MultiEntry import create_sku_analytics_bulk, create_skus_bulk
from uzum.product.models import Product, ProductAnalytics
from uzum.shop.models import Shop
from uzum.sku.models import Sku


def create_products_bulk(products):
    try:
        result = Product.objects.bulk_create(products, ignore_conflicts=True)
        print(f"createProductsBulk: {len(result)} objects inserted, {len(products) - len(result)} objects skipped")

        return {product.product_id: product for product in result}

    except Exception as e:
        print(f"Error in createProductsBulk: {e}")
        return None


def create_product_analytics_bulk(analytics):
    try:
        result = ProductAnalytics.objects.bulk_create(analytics, ignore_conflicts=True)
        print(f"createProductAnalyticsBulk: {len(result)} inserted, {len(analytics) - len(result)} skipped")
        return {analytic.product.product_id: analytic for analytic in result}

    except Exception as e:
        print(f"Error in createProductAnalyticsBulk: {e}")
        return None


def create_products_from_api(produts_api: list[dict]):
    try:
        print("Starting createProductsFromApi...")
        start_1 = time.time()
        products_data = []
        products_analytics = []
        product_skus = []
        product_skus_analytics = []
        shops_analytics = []
        shops_list = []

        products = {}
        for prod in get_all_products():
            products[prod.product_id] = prod

        skus = Sku.objects.all()
        skus_dict = {sku.sku: sku for sku in skus}
        shops = Shop.objects.all()
        shops_dict = {shop.seller_id: shop.seller_id for shop in shops}
        categories_dict = {category.categoryId: category.categoryId for category in Category.objects.all()}
        badges_dict = {badge.badge_id: badge for badge in Badge.objects.all()}
        badges_to_set = {}
        total_new_products = 0
        total_new_skus = [0, 0]
        shop_analytics_track = {}

        print("Starting update or create campaigns...")
        c_time = time.time()
        product_campaigns = update_or_create_campaigns()
        print(f"Finished update or create campaigns... - {time.time() - c_time}")

        print("Starting to prepare data...")
        for product in produts_api:
            (
                product_data,
                product_analytic,
                sku_list,
                sku_list_analytics,
                shop_analytics,
                shop,
                badges,
            ) = prepareProductData(
                product,
                products,
                skus_dict,
                shops_dict,
                categories_dict,
                shop_analytics_track,
                badges_dict,
            )

            products_analytics.append(product_analytic)
            product_skus_analytics.extend(sku_list_analytics)
            if len(badges) > 0:
                badges_to_set[product["id"]] = badges

            if shop_analytics:
                shops_analytics.append(shop_analytics)
            if shop:
                shops_list.append(shop)

            if product_data:
                products_data.append(product_data)
                total_new_products += 1

            if sku_list:
                product_skus.extend(sku_list)
                total_new_skus[0] += len(sku_list)
                total_new_skus[1] += 1

        if len(shops_list) > 0:
            print(f"Creating shops... - {len(shops_list)}")
            start = time.time()
            Shop.objects.bulk_create(shops_list, ignore_conflicts=True)
            end = time.time()
            print(f"Time taken to create shops: {end - start}")

        if len(products_data) > 0:
            print(f"Creating products... - {len(products_data)}")
            start = time.time()
            result = create_products_bulk(products_data)
            if badges_to_set:
                print("Setting badges...")
                badge_start = time.time()
                for product_id, badges in badges_to_set.items():
                    product = result.get(product_id, None)
                    if product:
                        product.badges.set(badges)
                        product.save()
                print(f"Time taken to set badges: {time.time() - badge_start}")
            end = time.time()
            print(f"Time taken to create products: {end - start}")
            time.sleep(3)
        if len(product_skus) > 0:
            start = time.time()
            print(f"Creating skus... - {len(product_skus)}")
            create_skus_bulk(product_skus)
            end = time.time()
            print(f"Time taken to create skus: {end - start}")
            time.sleep(3)

        print(f"Creating product analytics... - {len(products_analytics)}")
        start = time.time()
        result = create_product_analytics_bulk(products_analytics)
        if product_campaigns:
            print("Setting campaigns...")
            campaign_start = time.time()
            for product_id, campaigns in product_campaigns.items():
                if product_id in product_campaigns and len(campaigns) > 0:
                    temp = result.get(product_id)
                    if temp:
                        temp.campaigns.set(campaigns)
                        temp.save()
            print(f"Time taken to set campaigns: {time.time() - campaign_start}")
        end = time.time()
        print(f"Time taken to create product analytics: {end - start}")

        print(f"Creating sku analytics... - {len(product_skus_analytics)}")
        create_sku_analytics_bulk(product_skus_analytics)
        end_2 = time.time()
        print(f"Time taken to create sku analytics: {end_2 - end}")

        print(f"Creating shop analytics... - {len(shops_analytics)}")
        create_shop_analytics_bulk(shops_analytics)
        end_3 = time.time()
        print(f"Time taken to create shop analytics: {end_3 - end_2}")

        print(f"create_products_from_api completed - {time.time() - start_1}")

    except Exception as e:
        print(f"Error in createProductsFromApi: {e}")
        traceback.print_exc()
        return None


def get_all_products():
    try:
        return Product.objects.all()
    except Exception as e:
        print(f"Error in getAllProducts: {e}")
        return None
