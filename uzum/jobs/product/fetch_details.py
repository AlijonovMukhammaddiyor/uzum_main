import asyncio
import logging
import time

import httpx

from uzum.jobs.constants import PRODUCT_CONCURRENT_REQUESTS_LIMIT, PRODUCT_HEADER, PRODUCT_URL
from uzum.jobs.helpers import generateUUID, get_random_user_agent

# Set up a basic configuration for logging
logging.basicConfig(level=logging.INFO)

# Optionally, disable logging for specific libraries
logging.getLogger("httpx").setLevel(logging.WARNING)


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
                time.sleep(15)
                if len(failed_failed) > 0:
                    final_failed = []
                    print(
                        f"Failed failed Ids length: {len(failed_failed)}",
                    )
                    await concurrent_requests_product_details(failed_failed, final_failed, 0, products_api)
                    time.sleep(15)
                    if len(final_failed) > 0:
                        ff_failed = []
                        await concurrent_requests_product_details(final_failed, ff_failed, 0, products_api)
                        print(f"Total number of failed product ids: {len(ff_failed)}")
                        print(f"Failed failed Ids: {ff_failed}")

        print(f"Total number of products: {len(products_api)}")
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
        last_length = len(products_api)
        print(f"Starting concurrent_requests_product_details... {len(product_ids)}")
        async with httpx.AsyncClient() as client:
            while index < len(product_ids):
                if len(products_api) - last_length >= 1000:
                    string_to_show = f"Fetched: {len(products_api) - last_length}, Failed: {len(failed_ids)}"
                    print(
                        f"Current: {index}/ {len(product_ids)} - {time.time() - start_time:.2f} secs - {string_to_show}"
                    )
                    last_length = len(products_api)
                    time.sleep(2)  # sleep for 2 seconds
                    start_time = time.time()

                tasks = [
                    make_request_product_detail(
                        PRODUCT_URL + str(id),
                        client=client,
                    )
                    for id in product_ids[index : index + PRODUCT_CONCURRENT_REQUESTS_LIMIT]
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for idx, res in enumerate(results):
                    if isinstance(res, Exception):
                        print("Error in concurrent_requests_product_details A:", res)
                        failed_ids.append(product_ids[index + idx])
                    else:
                        if res.status_code != 200:
                            _id = product_ids[index + idx]
                            print(
                                f"Error in concurrent_requests_product_details B: {res.status_code} - {_id}",
                            )
                            failed_ids.append(product_ids[index + idx])
                            continue
                        # print(res.json())

                        res_data = res.json()
                        if "errors" not in res_data:
                            products_api.append(res_data["payload"]["data"])
                        else:
                            failed_ids.append(product_ids[index + idx])

                del results
                del tasks
                index += PRODUCT_CONCURRENT_REQUESTS_LIMIT

    except Exception as e:
        print(f"Error in concurrent_requests_product_details C: {e}")
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
