import asyncio
import logging
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from requests import Session
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


# async def concurrent_requests_product_details(
#     product_ids: list[int], failed_ids: list[int], index: int, products_api: list[dict]
# ):
#     try:
#         index = 0
#         start_time = time.time()
#         last_length = len(products_api)
#         print(f"Starting concurrent_requests_product_details... {len(product_ids)}")
#         async with httpx.AsyncClient() as client:
#             while index < len(product_ids):
#                 if len(products_api) - last_length >= 1000:
#                     string_to_show = f"Fetched: {len(products_api) - last_length}, Failed: {len(failed_ids)}"
#                     print(
#                         f"Current: {index}/ {len(product_ids)} - {time.time() - start_time:.2f} secs - {string_to_show}"
#                     )
#                     last_length = len(products_api)
#                     time.sleep(2)  # sleep for 2 seconds
#                     start_time = time.time()

#                 tasks = [
#                     make_request_product_detail(
#                         PRODUCT_URL + str(id),
#                         client=client,
#                     )
#                     for id in product_ids[index : index + PRODUCT_CONCURRENT_REQUESTS_LIMIT]
#                 ]

#                 results = await asyncio.gather(*tasks, return_exceptions=True)

#                 for idx, res in enumerate(results):
#                     if isinstance(res, Exception):
#                         print("Error in concurrent_requests_product_details A:", res)
#                         failed_ids.append(product_ids[index + idx])
#                     else:
#                         if res.status_code != 200:
#                             _id = product_ids[index + idx]
#                             if res.status_code == 429:
#                                 retry_after = res.headers.get('Retry-After', -7)
#                                 if retry_after != -7:
#                                     print(f"Rate limit exceeded. Try again in {retry_after} seconds.")
#                             print(
#                                 f"Error in concurrent_requests_product_details B: {res.status_code} - {_id}",
#                             )
#                             failed_ids.append(product_ids[index + idx])
#                             continue
#                         # print(res.json())

#                         res_data = res.json()
#                         if "errors" not in res_data:
#                             products_api.append(res_data["payload"]["data"])
#                         else:
#                             failed_ids.append(product_ids[index + idx])

#                 del results
#                 del tasks
#                 index += PRODUCT_CONCURRENT_REQUESTS_LIMIT

#     except Exception as e:
#         print(f"Error in concurrent_requests_product_details C: {e}")
#         return None


# async def make_request_product_detail(url, retries=3, backoff_factor=0.3, client=None):
#     for i in range(retries):
#         try:
#             response = await client.get(
#                 url,
#                 headers={
#                     **PRODUCT_HEADER,
#                     "User-Agent": get_random_user_agent(),
#                     "x-iid": generateUUID(),
#                 },
#                 timeout=60,  # 60 seconds
#             )

#             if response.status_code == 200:
#                 return response
#             if i == retries - 1:
#                 return response
#         except Exception as e:
#             if i == retries - 1:  # This is the last retry, raise the exception
#                 print("Sleeping for 5 seconds...")
#                 await asyncio.sleep(5)
#                 raise e
#             else:
#                 print(f"Error in make_request_product_detail (attempt {i + 1}):{url}")
#                 print(e)
#                 sleep_time = backoff_factor * (2**i)
#                 # time.sleep(sleep_time)
#                 await asyncio.sleep(sleep_time)

# Constants
CHUNK_SIZE = 60  # Number of requests in each chunk
MAX_RETRIES = 3  # Total retries for each request
BACKOFF_FACTOR = 0.3  # Factor for calculating the sleep time between retries
RATE_LIMIT_SLEEP = 2  # Sleep time when rate limit is exceeded (in seconds)
RETRY_ATTEMPTS = 3  # Total number of attempts for each request
SLEEP_ON_RATE_LIMIT = 2  # Sleep time when rate limit is exceeded (in seconds)


def make_request_product_detail(url, session):
    """Make a single request with retries in case of failure."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = session.get(
                url,
                headers={
                    **PRODUCT_HEADER,
                    "User-Agent": get_random_user_agent(),
                    "x-iid": generateUUID(),
                },
                timeout=60  # 60 seconds timeout
            )
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                print(f"Rate limit exceeded. Sleeping for {SLEEP_ON_RATE_LIMIT} seconds.")
                time.sleep(SLEEP_ON_RATE_LIMIT)  # Sleeping if rate limit is exceeded
        except requests.RequestException as e:
            print(f"Request failed (attempt {attempt + 1}): {e}")
            if attempt < RETRY_ATTEMPTS - 1:
                sleep_time = BACKOFF_FACTOR * (2 ** attempt)
                time.sleep(sleep_time)  # Backoff before retrying
            else:
                # Last attempt
                return None

def fetch_product_details_chunk(product_ids_chunk, session):
    """Fetch details for a chunk of product IDs."""
    products_api_chunk = []
    failed_ids_chunk = []

    session = create_session(100)

    with ThreadPoolExecutor(max_workers=CHUNK_SIZE) as executor:
        future_to_url = {
            executor.submit(make_request_product_detail, PRODUCT_URL + str(product_id), session): product_id for product_id in product_ids_chunk
        }

        for future in as_completed(future_to_url):
            product_id = future_to_url[future]
            try:
                response = future.result()
                if response is not None and response.status_code == 200:
                    data = response.json()
                    if "errors" not in data:
                        products_api_chunk.append(data["payload"]["data"])
                    else:
                        print(f"Error for product {product_id}: {data['errors']}")
                        failed_ids_chunk.append(product_id)
                else:
                    print(f"Failed request for product {product_id}.")
                    failed_ids_chunk.append(product_id)
            except Exception as exc:
                print(f"Generated an exception for {product_id}: {exc}")
                failed_ids_chunk.append(product_id)

    return products_api_chunk, failed_ids_chunk


def concurrent_requests_product_details(product_ids, failed_ids: list[int], index, products_api):
    with requests.Session() as session:
        # We divide the product_ids list into chunks.
        for i in range(0, len(product_ids), CHUNK_SIZE):
            product_ids_chunk = product_ids[i:i + CHUNK_SIZE]
            products_chunk, failed_chunk = fetch_product_details_chunk(product_ids_chunk, session)

            products_api.extend(products_chunk)
            failed_ids.extend(failed_chunk)

            if failed_chunk:
                print(f"Failed IDs in this chunk: {failed_chunk}")

            # If we hit the rate limit, we should pause the requests.
            if len(failed_chunk) > 0 and any(id.endswith('429') for id in failed_chunk):  # Check if any ID ends with 429, indicating a rate limit error
                print(f"Rate limit likely exceeded. Sleeping for {RATE_LIMIT_SLEEP} seconds before continuing with the next chunk.")
                time.sleep(RATE_LIMIT_SLEEP)

def create_session(max_connections):
    session = Session()

    # Define a retry strategy to add resilience to your requests
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        method_whitelist=["HEAD", "GET", "OPTIONS"]
    )

    # Attach the retry strategy to an HTTPAdapter with an increased connection pool size
    adapter = HTTPAdapter(pool_connections=max_connections, pool_maxsize=max_connections, max_retries=retries)
    session.mount('https://', adapter)
    session.mount('http://', adapter)

    return session
