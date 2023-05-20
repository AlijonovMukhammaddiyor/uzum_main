
from uzum.jobs.constants import PAGE_SIZE
from uzum.jobs.product.fetch_details import get_product_details_via_ids
from uzum.jobs.product.fetch_ids import get_all_product_ids_from_uzum


async def create_and_update_products(filtered_categories):
    print("create_and_update_products started")
    # 1. Get all categories which have less than N products

    if not filtered_categories:
        print("No categories found")
        return
    # 2. Get all product ids from uzum
    product_ids: list[int] = []
    await get_all_product_ids_from_uzum(
        filtered_categories,
        product_ids,
        page_size=PAGE_SIZE,
    )

    product_ids = list(set(product_ids))

    # 3. Fetch all products from uzum using product ids
    # products_api: list[dict] = []
    # await get_product_details_via_ids(product_ids, products_api)

    # UNTIL here, everything is alright

    # return products_api
