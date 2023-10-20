import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import requests
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from uzum.jobs.constants import (PRODUCT_CONCURRENT_REQUESTS_LIMIT,
                                 PRODUCT_HEADER, PRODUCT_URL)
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
            await concurrent_requests_product_details(failed_ids, failed_again_ids, 0, products_api)

            if len(failed_again_ids) > 0:
                failed_failed = []
                print(f"Failed again Ids length: {len(failed_again_ids)}")
                await concurrent_requests_product_details(failed_again_ids, failed_failed, 0, products_api)

                if len(failed_failed) > 0:
                    final_failed = []
                    print(
                        f"Failed failed Ids length: {len(failed_failed)}",
                    )
                    await concurrent_requests_product_details(failed_failed, final_failed, 0, products_api)

                    if len(final_failed) > 0:
                        ff_failed = []
                        await concurrent_requests_product_details(final_failed, ff_failed, 0, products_api)

                        print(f"Total number of failed product ids: {len(ff_failed)}")
                        print(f"Failed failed Ids: {ff_failed}")

                        if len(ff_failed) > 0:
                            fff_failed = []
                            await concurrent_requests_product_details(ff_failed, fff_failed, 0, products_api)

                            print(f"Total number of failed product ids: {len(fff_failed)}")
                            print(f"Failed failed Ids: {fff_failed}")

                            if len(fff_failed) > 0:
                                ffff_failed = []
                                await concurrent_requests_product_details(fff_failed, ffff_failed, 0, products_api)

                                print(f"Total number of failed product ids: {len(ffff_failed)}")
                                print(f"Failed failed Ids: {ffff_failed}")

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
        errors = {}
        index = 0
        start_time = time.time()
        last_length = len(products_api)
        print(f"Starting concurrent_requests_product_details... {len(product_ids)}")
        async with httpx.AsyncClient() as client:
            while index < len(product_ids):
                # update the client, cut the session and create a new one
                # client = httpx.AsyncClient()
                if len(products_api) - last_length >= 1000:
                    string_to_show = f"Fetched: {len(products_api) - last_length}, Failed: {len(failed_ids)}"
                    print(
                        f"Current: {index}/ {len(product_ids)} - {time.time() - start_time:.2f} secs - {string_to_show}"
                    )
                    last_length = len(products_api)
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
                        failed_ids.append(product_ids[index + idx])
                    else:
                        if res.status_code != 200:
                            _id = product_ids[index + idx]
                            failed_ids.append(product_ids[index + idx])
                            # print(f"Failed request for product {_id} - {res.status_code}")
                            if res.status_code not in errors:
                                errors[res.status_code] = []
                            errors[res.status_code].append(_id)
                            continue

                        res_data = res.json()
                        if "errors" not in res_data:
                            products_api.append(res_data["payload"]["data"])
                        else:
                            failed_ids.append(product_ids[index + idx])

                del results
                del tasks
                index += PRODUCT_CONCURRENT_REQUESTS_LIMIT
        print(errors)
        for key, value in errors.items():
            print(f"Status code: {key}, Count: {len(value)}")

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
                timeout=20,  # 60 seconds
            )

            if response.status_code == 200 or response.status_code == 429:
                return response
            if i == retries - 1:
                return response
        except Exception as e:
            if i == retries - 1:  # This is the last retry, raise the exception
                print("Sleeping for 5 seconds...")
                await asyncio.sleep(2)
                raise e
            else:
                print(f"Error in make_request_product_detail (attempt {i + 1}):{url}")
                print(e)
                sleep_time = backoff_factor * (2**i)
                # time.sleep(sleep_time)
                await asyncio.sleep(sleep_time)

# Constants
CHUNK_SIZE = 5  # Number of requests in each chunk
MAX_RETRIES = 3  # Total retries for each request
BACKOFF_FACTOR = 0.3  # Factor for calculating the sleep time between retries
RATE_LIMIT_SLEEP = 2  # Sleep time when rate limit is exceeded (in seconds)
RETRY_ATTEMPTS = 3  # Total number of attempts for each request
SLEEP_ON_RATE_LIMIT = 2  # Sleep time when rate limit is exceeded (in seconds)


# def make_request_product_detail(url, session):
#     """Make a single request with retries in case of failure."""
#     for attempt in range(RETRY_ATTEMPTS):
#         try:
#             response = session.get(
#                 url,
#                 headers={
#                     **PRODUCT_HEADER,
#                     "User-Agent": get_random_user_agent(),
#                     "x-iid": generateUUID(),
#                 },
#                 timeout=60  # 60 seconds timeout
#             )
#             if response.status_code == 200:
#                 return response
#             elif response.status_code == 429:
#                 print(f"Rate limit exceeded. Sleeping for {SLEEP_ON_RATE_LIMIT} seconds.")
#                 time.sleep(SLEEP_ON_RATE_LIMIT)  # Sleeping if rate limit is exceeded
#         except requests.RequestException as e:
#             print(f"Request failed (attempt {attempt + 1}): {e}")
#             if attempt < RETRY_ATTEMPTS - 1:
#                 sleep_time = BACKOFF_FACTOR * (2 ** attempt)
#                 time.sleep(sleep_time)  # Backoff before retrying
#             else:
#                 # Last attempt
#                 return None

# def fetch_product_details_chunk(product_ids_chunk, session):
#     """Fetch details for a chunk of product IDs."""
#     products_api_chunk = []
#     failed_ids_chunk = []

#     # session = create_session(MAX_RETRIES, 100)

#     with ThreadPoolExecutor(max_workers=CHUNK_SIZE) as executor:
#         future_to_url = {
#             executor.submit(make_request_product_detail, PRODUCT_URL + str(product_id), session): product_id for product_id in product_ids_chunk
#         }

#         for future in as_completed(future_to_url):
#             product_id = future_to_url[future]
#             try:
#                 response = future.result()
#                 if response is not None and response.status_code == 200:
#                     data = response.json()
#                     if "errors" not in data:
#                         products_api_chunk.append(data["payload"]["data"])
#                     else:
#                         print(f"Error for product {product_id}: {data['errors']}")
#                         failed_ids_chunk.append(product_id)
#                 else:
#                     print(f"Failed request for product {product_id}.")
#                     failed_ids_chunk.append(product_id)
#             except Exception as exc:
#                 print(f"Generated an exception for {product_id}: {exc}")
#                 failed_ids_chunk.append(product_id)

#     return products_api_chunk, failed_ids_chunk


# def concurrent_requests_product_details(product_ids, failed_ids: list[int], index, products_api):
#     start = time.time()
#     session = create_session(MAX_RETRIES, 100)
#     last_length = len(products_api)

#     for i in range(0, len(product_ids), CHUNK_SIZE):
#         if len(products_api) - last_length >= 1000:
#             string_to_show = f"Fetched: {len(products_api) - last_length}, Failed: {len(failed_ids)}"
#             print(
#                 f"Current: {i}/{len(product_ids)} - {time.time() - start:.2f} secs - {string_to_show}"
#             )
#             last_length = len(products_api)
#             time.sleep(2)
#         product_ids_chunk = product_ids[i:i + CHUNK_SIZE]
#         products_chunk, failed_chunk = fetch_product_details_chunk(product_ids_chunk, session)
#         time.sleep(SLEEP_ON_RATE_LIMIT)

#         products_api.extend(products_chunk)
#         failed_ids.extend(failed_chunk)

#         if failed_chunk:
#             print(f"Failed IDs in this chunk: {failed_chunk}")

#     print(f"Total time taken by concurrent_requests_product_details: {time.time() - start}")

# def create_session(max_retries=3, max_connections=100):
#     session = requests.Session()
#     retries = Retry(
#         total=max_retries,
#         backoff_factor=BACKOFF_FACTOR,

#         status_forcelist=[429, 500, 502, 503, 504],  # Retry on specific HTTP status codes
#         method_whitelist=["HEAD", "GET", "OPTIONS"]
#     )
#     adapter = HTTPAdapter(pool_connections=max_connections, pool_maxsize=max_connections, max_retries=retries)
#     session.mount("http://", adapter)
#     session.mount("https://", adapter)
#     return session
