from uzum.jobs.category.MultiEntry import get_categories_with_less_than_n_products
from uzum.jobs.constants import MAX_OFFSET, PAGE_SIZE
from uzum.jobs.product.MultiEntry import create_products_from_api
from uzum.jobs.product.utils import (
    get_all_product_ids_from_uzum,
    get_product_details_via_ids,
)


def create_and_update_products():
    print("create_and_update_products started")
    # 1. Get all categories which have less than N products

    categories = get_categories_with_less_than_n_products(MAX_OFFSET + PAGE_SIZE)
    if not categories:
        print("No categories found")
        return
    # 2. Get all product ids from uzum
    product_ids: list[int] = []
    get_all_product_ids_from_uzum(
        categories,
        product_ids,
        page_size=PAGE_SIZE,
    )

    product_ids = list(set(product_ids))

    # 3. Fetch all products from uzum using product ids
    products_api: list[dict] = []
    get_product_details_via_ids(product_ids, products_api)

    # 4. Create products and skus
    create_products_from_api(products_api)
