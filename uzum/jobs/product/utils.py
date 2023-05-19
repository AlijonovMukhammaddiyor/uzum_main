import math
import json
from datetime import datetime
import pytz
import time
import traceback
import asyncio
import httpx
from uzum.badge.models import Badge
from uzum.category.models import Category
from uzum.jobs.badge.singleEntry import create_badge
from uzum.jobs.category.singleEntry import (
    create_category,
    create_category_analytics,
)

import logging

# Set up a basic configuration for logging
logging.basicConfig(level=logging.INFO)

# Optionally, disable logging for specific libraries
logging.getLogger("httpx").setLevel(logging.WARNING)

from uzum.jobs.constants import (
    CATEGORIES_HEADER,
    MAX_OFFSET,
    MAX_PAGE_SIZE,
    PRODUCT_CONCURRENT_REQUESTS_LIMIT,
    PRODUCT_HEADER,
    PRODUCT_URL,
    PRODUCTIDS_CONCURRENT_REQUESTS,
    PRODUCTS_URL,
)
from uzum.jobs.helpers import generateUUID, get_random_user_agent, products_payload
from uzum.product.models import Product, ProductAnalytics
from uzum.shop.models import Shop, ShopAnalytics
from uzum.sku.models import Sku, SkuAnalytics


async def get_all_product_ids_from_uzum(categories_dict: list[dict], product_ids, page_size: int):
    try:
        print("\n\nStarting getAllProductIdsFromUzum...")
        start_time = time.time()
        promises = []

        current_index = 0
        while current_index < len(categories_dict):
            # while current_index < 1:
            current_id = categories_dict[current_index]["categoryId"]
            current_category = categories_dict[current_index]
            # print("current_category: ", current_category)
            current_total = min(current_category["totalProducts"], MAX_OFFSET + MAX_PAGE_SIZE)
            req_count = math.ceil(current_total / page_size)

            current_offset = 0
            current_req_index = 0

            # for each category, we have to make multiple requests
            while current_req_index < req_count and current_offset < current_total:
                promises.append(
                    {
                        "categoryId": current_id,
                        "total": current_total,
                        "offset": current_offset,
                        "pageSize": page_size,
                    }
                )

                current_offset += page_size
                current_req_index += 1
            current_index += 1
        # print(promises)
        print(f"Total number of requests: {len(promises)}")

        failed_ids = []
        await concurrent_requests_for_ids(promises, 0, product_ids, failed_ids)
        if len(failed_ids) > 0:
            failed_again_ids = []
            print(f"Failed Ids length: {len(failed_ids)}")
            await concurrent_requests_for_ids(failed_ids, 0, product_ids, failed_again_ids)

            if len(failed_again_ids) > 0:
                final_failed_ids = []
                await concurrent_requests_for_ids(failed_again_ids, 0, product_ids, final_failed_ids)

                print(f"Total number of failed product ids: { len(final_failed_ids)}")

        print(f"Total number of product ids: {len(product_ids)}")
        print(f"Total number of unique product ids: {len(set(product_ids))}")
        print(
            f"Total time taken by get_all_product_ids_from_uzum: {time.time() - start_time}",
        )
        print("Ending getAllProductIdsFromUzum...\n\n")
    except Exception as e:
        print("Error in getAllProductIdsFromUzum: ", e)
        traceback.print_exc()
        return None


async def concurrent_requests_for_ids(data: list[dict], index: int, product_ids: list[int], failed_ids: list[int]):
    try:
        index = 0
        start_time = time.time()
        last_length = 0
        async with httpx.AsyncClient() as client:
            while index < len(data):
                # while index < 1:
                if len(product_ids) - last_length > 4000:
                    print(
                        f"Current index of productIds: {index}/ {len(data)} - {time.time() - start_time} seconds - {len(product_ids) - last_length} added - {len(failed_ids)} failed"
                    )
                    start_time = time.time()
                    time.sleep(3)
                    last_length = len(product_ids)

                tasks = [
                    make_request_product_ids(
                        products_payload(
                            promise["offset"],
                            promise["pageSize"],
                            promise["categoryId"],
                        ),
                        client=client,
                    )
                    for promise in data[index: index + PRODUCTIDS_CONCURRENT_REQUESTS]
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for idx, res in enumerate(results):
                    if isinstance(res, Exception):
                        print("Error in concurrentRequestsForIds inner:", res)
                        failed_ids.append(data[index + idx])
                    else:
                        res_data = res.json()
                        if "errors" not in res_data:
                            products = res_data["data"]["makeSearch"]["items"]
                            for product in products:
                                product_ids.append(product["catalogCard"]["productId"])
                        else:
                            failed_ids.append(data[index + idx]["categoryId"])

                index += PRODUCTIDS_CONCURRENT_REQUESTS

                # with ThreadPoolExecutor(max_workers=PRODUCTIDS_CONCURRENT_REQUESTS) as executor:
                #     futures = {
                #         executor.submit(
                #             make_request_product_ids,
                #             products_payload(
                #                 promise["offset"],
                #                 promise["pageSize"],
                #                 promise["categoryId"],
                #             ),
                #             session=session,
                #         ): promise
                #         for promise in data[index : index + PRODUCTIDS_CONCURRENT_REQUESTS]
                #     }
                #     for future in as_completed(futures):
                #         promise = futures[future]
                #         try:
                #             res = future.result()
                #             res_data = res.json()
                #             if "errors" not in res_data:
                #                 products = res_data["data"]["makeSearch"]["items"]
                #                 for product in products:
                #                     product_ids.append(product["catalogCard"]["productId"])
                #             else:
                #                 failed_ids.append(promise["categoryId"])

                #         except Exception as e:
                #             print("Error in concurrentRequestsForIds inner: ", e, promise)
                #             failed_ids.append(promise)

                # index += PRODUCTIDS_CONCURRENT_REQUESTS

    except Exception as e:
        print("Error in concurrentRequestsForIds: ", e)
        traceback.print_exc()
        return None


async def make_request_product_ids(
    data,
    retries=3,
    backoff_factor=0.3,
    client=None,
):
    for i in range(retries):
        try:
            return await client.post(
                PRODUCTS_URL,
                json=data,
                headers={
                    **CATEGORIES_HEADER,
                    "User-Agent": get_random_user_agent(),
                    "x-iid": generateUUID(),
                },
            )
        except Exception as e:
            if i == retries - 1:  # This is the last retry, raise the exception
                raise e
            print(f"Error in makeRequestProductIds (attemp:{i}): ", e)
            sleep_time = backoff_factor * (2**i)
            await asyncio.sleep(sleep_time)


async def get_product_details_via_ids(product_ids: list[int], products_api: list[dict]):
    try:
        print("Starting get_product_details_via_ids...")
        start_time = time.time()
        failed_ids = []

        await concurrent_requests_product_details(product_ids, failed_ids, 0, products_api)

        if len(failed_ids) > 0:
            failed_again_ids = []
            print(f"Failed Ids length: {len(failed_ids)}")
            time.sleep(5)
            await concurrent_requests_product_details(failed_ids, failed_again_ids, 0, products_api)

            if len(failed_again_ids) > 0:
                failed_failed = []
                print(f"Failed again Ids length: {len(failed_again_ids)}")
                await concurrent_requests_product_details(failed_again_ids, failed_failed, 0, products_api)
                time.sleep(5)
                if len(failed_failed) > 0:
                    final_failed = []
                    print(
                        f"Failed failed Ids length: {len(failed_failed)}",
                    )
                    await concurrent_requests_product_details(failed_failed, final_failed, 0, products_api)
                    print(f"Total number of failed product ids: {len(final_failed)}")
                    print(f"Failed failed Ids: {final_failed}")

        print("Total number of products: ", len(products_api))
        print(f"Total time taken by get_product_details_via_ids: {time.time() - start_time}")
        print("Ending get_product_details_via_ids...\n\n")
    except Exception as e:
        print("Error in getProductDetailsViaId: ", e)
        return None


async def concurrent_requests_product_details(
    product_ids: list[int], failed_ids: list[int], index: int, products_api: list[dict]
):
    try:
        index = 0
        start_time = time.time()
        last_length = 0
        async with httpx.AsyncClient() as client:
            while index < len(product_ids):
                if len(products_api) - last_length >= 1000:
                    print(
                        f"Current index of productIds: {index}/ {len(product_ids)} - {time.time() - start_time} seconds - {len(products_api) - last_length} products added - {len(failed_ids)} failed"
                    )
                    last_length = len(products_api)
                    time.sleep(2)  # sleep for 2 seconds
                    start_time = time.time()

                tasks = [
                    make_request_product_detail(
                        PRODUCT_URL + str(id),
                        client=client,
                    )
                    for id in product_ids[index: index + PRODUCT_CONCURRENT_REQUESTS_LIMIT]
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for idx, res in enumerate(results):
                    if isinstance(res, Exception):
                        print("Error in concurrent_requests_product_details inner:", res)
                        failed_ids.append(product_ids[index + idx])
                    else:
                        if res.status_code != 200:
                            print(
                                f"Error in concurrent_requests_product_details inner: {res.status_code} - {product_ids[index + idx]}",
                            )
                            failed_ids.append(product_ids[index + idx])
                            continue
                        # print(res.json())

                        res_data = res.json()
                        if "errors" not in res_data:
                            products_api.append(res_data["payload"]["data"])
                        else:
                            failed_ids.append(product_ids[index + idx])

                index += PRODUCT_CONCURRENT_REQUESTS_LIMIT

    except Exception as e:
        print(f"Error in concurrent_requests_product_details: {e}")
        return None


async def make_request_product_detail(url, retries=3, backoff_factor=0.3, client=None):
    for i in range(retries):
        try:
            response = await client.get(
                url,
                headers={
                    **PRODUCT_HEADER,
                    "User-Agent": get_random_user_agent(),
                    "x-iid": generateUUID(),
                },
                timeout=60,  # 60 seconds
            )

            if response.status_code == 200:
                return response
            if i == retries - 1:
                return response
        except Exception as e:
            if i == retries - 1:  # This is the last retry, raise the exception
                print("Sleeping for 5 seconds...")
                await asyncio.sleep(5)
                raise e
            else:
                print(f"Error in make_request_product_detail (attempt {i + 1}):{url}")
                print(e)
                sleep_time = backoff_factor * (2**i)
                # time.sleep(sleep_time)
                await asyncio.sleep(sleep_time)


def prepareProductData(
    product_api: dict,
    existing_products: dict,
    skus_dict: dict,
    shops_dict: dict,
    categories_dict: dict,
    shop_analytics_track: dict,
    badges_dict: dict,
):
    try:
        result = None
        skus = []
        sku_analytics = []
        shop = None
        shop_analytic = None

        # category
        category_id = product_api["category"]["id"]
        if category_id not in categories_dict:
            print("Category does not exist", category_id)
            category = create_category(
                categoryId=category_id,
                title=product_api["category"]["title"],
            )
            create_category_analytics(
                categoryId=category_id,
                totalProducts=product_api["category"]["productAmount"],
            )
            categories_dict[category_id] = category.categoryId
            try:
                parent_cat = Category.objects.get(categoryId=product_api["category"]["parent"]["id"])
                category.parent = parent_cat
                category.save()
                parent_cat.children.add(category)
                parent_cat.save()
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
        elif seller["id"] not in shop_analytics_track:
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
                        "textColor": badge_api["textColor"],
                        "backgroundColor": badge_api["backgroundColor"],
                        "description": badge_api["description"],
                    }
                )
                badges_dict[badge_id] = badge
                badges.append(badge)
            else:
                badges.append(badges_dict[badge_id])

        # just update the product
        if product_api["id"] in existing_products:
            product: Product = existing_products[product_api["id"]]
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

            # badges ManyToMany field. Compare badges(list of badge objects) with product.badges(list of badge objects)
            # if they are not equal, then update the product
            if len(badges) != product.badges.count():
                product.badges.set(badges)
                is_modified = True
            else:
                badges = set(badges)
                existing_badges = set(product.badges.all())

                for badge in badges:
                    if badge not in existing_badges:
                        product.badges.add(badge)
                        is_modified = True

                for badge in existing_badges:
                    if badge not in badges:
                        product.badges.remove(badge)
                        is_modified = True

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

            # result.badges.set(badges.map(lambda badge: badge.badge_id))
            # result.badges.set(list(map(lambda badge: badge.badge_id, badges)))
        # analytics
        analytics = {
            "created_at": datetime.now(tz=pytz.timezone("Asia/Tashkent")),
            "reviews_amount": product_api["reviewsAmount"],
            "rating": product_api["rating"],
            "orders_amount": product_api["ordersAmount"],
            "product_id": product_api["id"],
            # "campaigns": product_campaigns_dict[product_api["id"]],
        }
        for sku_api in product_api["skuList"]:
            sku, sku_analytic = prepareSku(
                sku_api,
                product_api["id"],
                product_api["characteristics"],
                skus_dict=skus_dict,
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


def prepareSku(sku_api: dict, product_id: int, characteristics: list[dict], skus_dict: dict):
    try:
        analytics = {}
        sku_dict = None

        if sku_api["id"] in skus_dict:
            # it already exists

            sku: Sku = skus_dict[sku_api["id"]]
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
                            "backgroundColor": sku_api["discountBadge"].get("backgroundColor", None),
                            "textColor": sku_api["discountBadge"].get("textColor", None),
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
        url = photo_obj["photo"]["24034"]["high"]
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
