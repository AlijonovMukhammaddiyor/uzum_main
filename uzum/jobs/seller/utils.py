import asyncio
import json
import time
import traceback
import httpx
import requests
from datetime import datetime
from django.db.models import Q
from uzum.jobs.constants import SELLER_HEADERS, SELLER_URL
from uzum.jobs.helpers import generateUUID, get_random_user_agent
from uzum.shop.models import Shop
from asgiref.sync import async_to_sync


async def fetch_shop_api(link: str, retries=3, backoff_factor=0.3, client=None):
    for i in range(retries):
        try:
            response = await client.get(
                SELLER_URL + link + "?categoryId=1",
                headers={
                    **SELLER_HEADERS,
                    "User-Agent": get_random_user_agent(),
                    "x-iid": generateUUID(),
                },
                timeout=60,
            )
            if response.status_code == 200:
                data: dict = response.json()
                return data.get("payload")
            if i == retries - 1:
                return None
        except Exception as e:
            if i == retries - 1:
                print("Sleeping for 5 seconds...")
                time.sleep(5)
                raise e
            else:
                print(f"Error in fetch_shop_api (attempt {i + 1}):{link}")
                print(e)
                sleep_time = backoff_factor * (2**i)
                time.sleep(sleep_time)


def sync_update_shop_credentials(links):
    async_to_sync(update_shop_credentials)(links)


async def update_shop_credentials(shop_links: list[str]):
    try:
        index = 0
        start_time = time.time()
        shop_results = []
        last_length = 0
        failed_links = []
        batch_size = 100
        currentIndex = 0

        while currentIndex < len(shop_links):
            currentIndex += batch_size
            async with httpx.AsyncClient() as client:
                while index < currentIndex:
                    if len(shop_results) - last_length >= 1000:
                        string_to_show = f"Fetched: {len(shop_results) - last_length}, Failed: {len(failed_links)}"
                        print(
                            f"Current: {index}/ {len(shop_links)} - {time.time() - start_time:.2f} secs - {string_to_show}"
                        )
                        last_length = len(shop_results)
                        time.sleep(2)  # sleep for 2 seconds
                        start_time = time.time()

                    tasks = [
                        fetch_shop_api(
                            link,
                            client=client,
                        )
                        for link in shop_links[index:currentIndex]
                    ]

                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for idx, res in enumerate(results):
                        if isinstance(res, Exception):
                            print("Error in shops update A:", res)
                            failed_links.append(shop_links[index + idx])
                        else:
                            if res is None:
                                _id = shop_links[index + idx]
                                print(
                                    f"Error in shops update B: {_id}",
                                )
                                failed_links.append(shop_links[index + idx])
                                continue
                            else:
                                shop_results.append(res)

                    del results
                    del tasks
                    index = currentIndex

            currentIndex += batch_size

        print(f"Failed links: {len(failed_links)}")
        with open("data.json", "w") as json_file:
            json.dump(failed_links, json_file, indent=4)

        # Now update shops
        # update_shops(shop_results)
    except Exception as e:
        print("Error in update_shop_credentials: ", e)
        traceback.print_exc()
        return None


def update_shops(shops_api: list[dict]):
    try:
        to_update = []
        to_create = []
        existing_seller_ids = Shop.objects.filter(seller_id__in=[data["id"] for data in shops_api]).values_list(
            "seller_id", flat=True
        )

        for data in shops_api:
            fields = {
                "avatar": data["avatar"],
                "banner": data["banner"],
                "description": data["description"],
                "has_charity_products": data["hasCharityProducts"],
                "link": data["link"],
                "official": data["official"],
                "info": json.dumps(data["info"]),  # Assuming you've imported json
                "title": data["title"],
                "account_id": data["sellerAccountId"],
            }

            if data["id"] in existing_seller_ids:
                # prepare for update
                shop = Shop(seller_id=data["id"], **fields)
                to_update.append(shop)
            # else:
            #     # prepare for creation
            #     print("Creating new shop: ", data["id"])
            #     shop = Shop(seller_id=data["id"], **fields)
            #     to_create.append(shop)

        # Now perform bulk update and bulk create
        if to_update:
            Shop.objects.bulk_update(to_update, fields.keys())

        if to_create:
            Shop.objects.bulk_create(to_create)

    except Exception as e:
        print("Error in update_shops: ", e)
        traceback.print_exc()
        return None
