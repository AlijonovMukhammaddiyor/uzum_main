import json
import traceback
from datetime import datetime

import pytz

from uzum.badge.models import Badge
from uzum.category.models import Category
from uzum.jobs.badge.singleEntry import create_badge
from uzum.jobs.category.singleEntry import create_category, create_category_analytics, find_category
from uzum.jobs.product.singleEntry import find_product
from uzum.jobs.sku.singleEntry import find_sku
from uzum.product.models import Product, ProductAnalytics
from uzum.shop.models import Shop, ShopAnalytics
from uzum.sku.models import Sku, SkuAnalytics


def prepareProductData(
    product_api: dict,
    shop_analytics_track: dict,
    shops_dict: dict,
    badges_dict: dict,
    shop_analytics_done: dict,
    current_analytic: dict = None,
    category_sales_map: dict = None,
    shop_links_and_titles: dict = None,
):
    try:
        result = None
        skus = []
        sku_analytics = []
        shop = None
        shop_analytic = None

        # category
        category_id = product_api["category"]["id"]
        current_category = find_category(category_id)
        if not current_category:
            print("Category does not exist", category_id)
            current_category = create_category(
                categoryId=category_id,
                title=product_api["category"]["title"],
            )
            create_category_analytics(
                categoryId=category_id,
                total_products=product_api["category"]["productAmount"],
            )
            try:
                # parent_cat = Category.objects.get(categoryId=product_api["category"]["parent"]["id"])
                parent_cat = find_category(product_api["category"]["parent"]["id"])
                if parent_cat:
                    current_category.parent = parent_cat
                    current_category.save()
            except Category.DoesNotExist:
                print("Parent category does not exist", category_id)

        # shop
        seller = product_api["seller"]
        if seller["id"] not in shops_dict:
            shop_, shop_analytic = prepare_seller_data(seller)
            shops_dict[seller["id"]] = seller["id"]
            shop = shop_
            shop_analytic = shop_analytic
            shop_analytics_track[seller["id"]] = True
        elif seller["id"] not in shop_analytics_track and seller["id"] not in shop_analytics_done:
            shop_analytic = ShopAnalytics(
                **{
                    "created_at": datetime.now(tz=pytz.timezone("Asia/Tashkent")),
                    "shop_id": seller["id"],
                    "total_products": seller["totalProducts"],
                    "total_orders": seller["orders"],
                    "total_reviews": seller["reviews"],
                    "rating": seller["rating"],
                }
            )

            shop_analytics_track[seller["id"]] = True
            shop_analytics_done[seller["id"]] = True

            # check if seller title and link is changed
            if seller["id"] in shop_links_and_titles and (
                shop_links_and_titles[seller["id"]][0] != seller["link"]
                or shop_links_and_titles[seller["id"]][1] != seller["title"]
            ):
                print("Seller title or link changed for", seller["id"])
                shop = Shop.objects.get(seller_id=seller["id"])
                shop.title = seller["title"]
                shop.link = seller["link"]
                shop.save()

        # badges
        badges_api = product_api["badges"]
        badges = []

        for badge_api in badges_api:
            badge_id = badge_api["id"]
            if badge_id not in badges_dict:
                badge = create_badge(
                    {
                        "badge_id": badge_api["id"],
                        "text": badge_api["text"],
                        "type": badge_api["type"],
                        "link": badge_api["link"],
                        "text_color": badge_api["textColor"],
                        "background_color": badge_api["backgroundColor"],
                        "description": badge_api["description"],
                    }
                )
                badges_dict[badge_id] = badge
                badges.append(badge)
            else:
                badges.append(badges_dict[badge_id])

        # just update the product
        current_product = find_product(product_api["id"])
        if current_product:
            product: Product = current_product
            is_modified = False
            if product.category.categoryId != category_id:
                product.category = Category.objects.get(categoryId=category_id)
                is_modified = True
            if product.is_eco != product_api["isEco"]:
                product.is_eco = product_api["isEco"]
                is_modified = True
            if product.is_perishable != product_api["isPerishable"]:
                product.is_perishable = product_api["isPerishable"]
                is_modified = True
            if product.volume_discount != product_api["volumeDiscount"]:
                product.volume_discount = product_api["volumeDiscount"]
                is_modified = True
            if product.video != product_api["video"]:
                product.video = product_api["video"]
                is_modified = True
            if product.title != product_api["title"]:
                product.title = product_api["title"]
                is_modified = True
            if product.description != product_api["description"]:
                product.description = product_api["description"]
                is_modified = True
            if product.bonus_product != product_api["bonusProduct"]:
                product.bonus_product = product_api["bonusProduct"]
                is_modified = True
            if product.adult != product_api["adultCategory"]:
                product.adult = product_api["adultCategory"]
                is_modified = True
            if product.attributes != json.dumps(product_api["attributes"]):
                product.attributes = json.dumps(product_api["attributes"])
                is_modified = True
            if product.characteristics != json.dumps(product_api["characteristics"]):
                product.characteristics = json.dumps(product_api["characteristics"])
                is_modified = True
            if product.comments != json.dumps(product_api["comments"]):
                product.comments = json.dumps(product_api["comments"])
                is_modified = True
            if product.photos != json.dumps(extract_product_photos(product_api["photos"])):
                product.photos = json.dumps(extract_product_photos(product_api["photos"]))
                is_modified = True
            if product.shop.seller_id != seller["id"]:
                try:
                    product.shop = Shop.objects.get(seller_id=seller["id"])
                    is_modified = True
                except Shop.DoesNotExist:
                    print("Shop does not exist", seller["id"])

            if is_modified:
                product.save()
        else:
            # new product
            result = {
                "category_id": category_id,
                "product_id": product_api["id"],
                "title": product_api["title"],
                "description": product_api["description"],
                "adult": product_api["adultCategory"],
                "bonus_product": product_api["bonusProduct"],
                "is_eco": product_api["isEco"],
                "is_perishable": product_api["isPerishable"],
                "volume_discount": product_api["volumeDiscount"],
                "video": product_api["video"],
                "attributes": json.dumps(product_api["attributes"]),
                "characteristics": json.dumps(product_api["characteristics"]),
                "comments": json.dumps(product_api["comments"]),
                "photos": json.dumps(extract_product_photos(product_api["photos"])),
                "shop_id": seller["id"],
            }

            result = Product(**result)

        # analytics
        latest_orders_amount = current_analytic["latest_orders_amount"] if current_analytic else 0
        # product_analytic["orders_money"] = (
        #         product_analytic["orders_amount"] - latest_orders_amount
        #     ) * product_analytic["average_purchase_price"]
        try:
            average_purchase_price = sum([sku["purchasePrice"] for sku in product_api["skuList"]]) / (
                len(product_api["skuList"] if len(product_api["skuList"]) > 0 else 1)
            )
        except Exception as e:
            print(e, product_api["skuList"], product_api["id"])
            traceback.print_exc()
            average_purchase_price = 0
        latest_orders_money = current_analytic["latest_orders_money"] if current_analytic else 0

        new_orders_money = latest_orders_money + (
            (
                (product_api["ordersAmount"] - latest_orders_amount)
                * (average_purchase_price if average_purchase_price else 0)
            )
            / 1000.0
        )

        if product_api["ordersAmount"] - latest_orders_amount > 0:
            if category_id not in category_sales_map:
                category_sales_map[category_id] = {"products_with_sales": set(), "shops_with_sales": set()}
            else:
                category_sales_map[category_id]["products_with_sales"].add(product_api["id"])
                # add sellers as well
                category_sales_map[category_id]["shops_with_sales"].add(seller["id"])

        analytics = {
            "created_at": datetime.now(tz=pytz.timezone("Asia/Tashkent")),
            "reviews_amount": product_api["reviewsAmount"],
            "rating": product_api["rating"],
            "available_amount": product_api["totalAvailableAmount"],
            "orders_amount": product_api["ordersAmount"],
            "product_id": product_api["id"],
            # get average of purchase_price from skuList
            "average_purchase_price": average_purchase_price if average_purchase_price else 0,
            "orders_money": max(new_orders_money, 0),
            # "title": product_api["title"],
            # "description": product_api["description"],
            # "photos": json.dumps(extract_product_photos(product_api["photos"])),
            # "attributes": json.dumps(product_api["attributes"]),
            # "characteristics": json.dumps(product_api["characteristics"]),
        }

        for sku_api in product_api["skuList"]:
            sku, sku_analytic = prepareSku(
                sku_api,
                product_api["id"],
                product_api["characteristics"],
            )
            if sku:
                skus.append(sku)
            sku_analytics.append(sku_analytic)

        skus = skus if len(skus) > 0 else None
        product_analytics = ProductAnalytics(**analytics)

        return (
            result,
            product_analytics,
            skus,
            sku_analytics,
            shop_analytic,
            shop,
            badges,
        )

    except Exception as e:
        print(f"Error in prepareProductData: {e}")
        traceback.print_exc()
        return None


def prepareSku(sku_api: dict, product_id: int, characteristics: list[dict]):
    try:
        analytics = {}
        sku_dict = None

        sku = find_sku(sku_api["id"])
        if sku:
            # it already exists
            is_modified = False

            if sku.barcode != sku_api["barcode"]:
                sku.barcode = sku_api["barcode"]
                is_modified = True
            if sku.charity_profit != sku_api["charityProfit"]:
                sku.charity_profit = sku_api["charityProfit"]
                is_modified = True
            if (
                len(sku_api["productOptionDtos"]) > 0
                and sku.payment_per_month != sku_api["productOptionDtos"][0]["paymentPerMonth"]
            ):
                sku.payment_per_month = sku_api["productOptionDtos"][0]["paymentPerMonth"]
                is_modified = True
            if sku.vat_amount != sku_api["vat"]["vatAmount"]:
                sku.vat_amount = sku_api["vat"]["vatAmount"]
                is_modified = True
            if sku.vat_price != sku_api["vat"]["price"]:
                sku.vat_price = sku_api["vat"]["price"]
                is_modified = True
            if sku.vat_rate != sku_api["vat"]["vatRate"]:
                sku.vat_rate = sku_api["vat"]["vatRate"]
                is_modified = True
            if sku.video_url != sku_api["videoUrl"]:
                sku.video_url = sku_api["videoUrl"]
                is_modified = True
            if sku.characteristics != prepare_sku_characteristics(sku_api["characteristics"], characteristics):
                sku.characteristics = prepare_sku_characteristics(sku_api["characteristics"], characteristics)
                is_modified = True
            if not sku_api["discountBadge"] and sku.discount_badge:
                sku.discount_badge = None
                is_modified = True
            elif (not sku.discount_badge and sku_api["discountBadge"]) or (
                sku.discount_badge
                and sku_api["discountBadge"]
                and sku.discount_badge.badge_id != sku_api["discountBadge"]["badgeId"]
            ):
                try:
                    badge = Badge.objects.get(badge_id=sku_api["discountBadge"]["badgeId"])
                except Badge.DoesNotExist:
                    badge = Badge.objects.create(
                        badge_id=sku_api["discountBadge"]["badgeId"],
                        title=sku_api["discountBadge"]["title"],
                        color=sku_api["discountBadge"]["color"],
                        image=sku_api["discountBadge"]["image"],
                    )
                sku.discount_badge = badge
                is_modified = True

            if is_modified:
                sku.save()

        else:
            sku_dict = {
                "sku": sku_api["id"],
                "barcode": sku_api["barcode"],
                "product_id": product_id,
                "charity_profit": sku_api["charityProfit"],
                "payment_per_month": sku_api["productOptionDtos"][0]["paymentPerMonth"]
                if len(sku_api["productOptionDtos"]) > 0
                else 0,
                "vat_amount": sku_api["vat"]["vatAmount"],
                "vat_price": sku_api["vat"]["price"],
                "vat_rate": sku_api["vat"]["vatRate"],
                "video_url": sku_api["videoUrl"],
                "characteristics": prepare_sku_characteristics(sku_api["characteristics"], characteristics),
                "discount_badge": None,
            }
            if sku_api["discountBadge"]:
                try:
                    badge = Badge.objects.get(badge_id=sku_api["discountBadge"]["badgeId"])
                except Badge.DoesNotExist:
                    try:
                        print(f"Creating new badge - {sku_api['discountBadge']['text']}")
                    except KeyError:
                        pass
                    badge = create_badge(
                        {
                            "badge_id": sku_api["discountBadge"]["badgeId"],
                            "description": sku_api["discountBadge"].get("description", None),
                            "text": sku_api["discountBadge"].get("text", None),
                            "type": sku_api["discountBadge"].get("type", None),
                            "link": sku_api["discountBadge"].get("link", None),
                            "background_color": sku_api["discountBadge"].get("backgroundColor", None),
                            "text_color": sku_api["discountBadge"].get("textColor", None),
                        }
                    )

                sku_dict["discount_badge"] = badge
            else:
                sku_dict["discount_badge"] = None
        analytics = {
            "created_at": datetime.now(tz=pytz.timezone("Asia/Tashkent")),
            "available_amount": sku_api["availableAmount"],
            "full_price": sku_api["fullPrice"],
            "purchase_price": sku_api["purchasePrice"],
            "sku_id": sku_api["id"],
        }

        sku_obj = Sku(**sku_dict) if sku_dict else None
        return sku_obj, SkuAnalytics(**analytics)
    except Exception as e:
        print(f"Error in prepareSku: {e}")
        traceback.print_exc()
        return None, None


def extract_product_photos(product_photos: list[dict]):
    photos = []
    for photo_obj in product_photos:
        url = photo_obj["photo"]["800"]["high"]
        photos.append(url)

    return photos


def prepare_sku_characteristics(sku_api_chars: dict, characteristics: list[dict]):
    char = []
    for charac in sku_api_chars:
        target_character = characteristics[charac["charIndex"]]
        title = target_character["title"]
        value = target_character["values"][charac["valueIndex"]]["title"]
        char.append({"title": title, "value": value})
    return json.dumps(char)


def prepare_seller_data(seller_data: dict):
    try:
        shop = Shop(
            **{
                "title": seller_data["title"],
                "seller_id": seller_data["id"],
                "avatar": seller_data["avatar"],
                "banner": seller_data["banner"],
                "description": seller_data["description"],
                "link": seller_data["link"],
                "has_charity_products": seller_data["hasCharityProducts"],
                "official": seller_data["official"],
                "info": json.dumps(seller_data["info"]),
                "registration_date": datetime.fromtimestamp(
                    seller_data["registrationDate"] / 1000,
                    tz=pytz.timezone("Asia/Tashkent"),
                ),
                "account_id": seller_data.get("sellerAccountId", None),
            }
        )

        shop_analytic = ShopAnalytics(
            **{
                "created_at": datetime.now(tz=pytz.timezone("Asia/Tashkent")),
                "shop_id": seller_data["id"],
                "total_products": seller_data["totalProducts"],
                "total_orders": seller_data["orders"],
                "total_reviews": seller_data["reviews"],
                "rating": seller_data["rating"],
            }
        )

        return shop, shop_analytic
    except Exception as e:
        print(f"Error in prepareSellerData: {e}")
        traceback.print_exc()
        return None
