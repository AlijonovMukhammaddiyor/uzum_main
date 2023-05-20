import asyncio
import logging
import math
import time
import traceback

import httpx

from uzum.jobs.constants import (
    CATEGORIES_HEADER,
    MAX_OFFSET,
    MAX_PAGE_SIZE,
    PRODUCTIDS_CONCURRENT_REQUESTS,
    PRODUCTS_URL,
)
from uzum.jobs.helpers import generateUUID, get_random_user_agent, products_payload

# Set up a basic configuration for logging
logging.basicConfig(level=logging.INFO)

# Optionally, disable logging for specific libraries
logging.getLogger("httpx").setLevel(logging.WARNING)


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
                    string_show = f"Fetched: {len(product_ids) - last_length}, Failed: {len(failed_ids)}"
                    print(
                        f"Current: {index}/ {len(data)} - {time.time() - start_time:.2} secs - {string_show}"
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

