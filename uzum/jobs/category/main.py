import time

from uzum.jobs.category.MultiEntry import (
    create_categories,
    create_category_analytics_bulk,
)
from uzum.jobs.category.utils import (
    assign_parents,
    get_categories_tree,
    prepare_categories_for_bulk_create,
)


def create_and_update_categories():
    try:
        start_time = time.time()
        print("createAndUpdateCategories started")
        categories_tree = get_categories_tree()
        print(f"createAndUpdateCategories: categories_tree fetched from uzum: {len(categories_tree)} ")

        cat_analytics = []
        new_categories = []
        cat_parents = []
        prepare_categories_for_bulk_create(
            categories_tree,
            cat_analytics,
            new_categories,
            cat_parents,
        )
        if len(new_categories) > 0:
            create_categories(new_categories)
        # sleep for 3 seconds. Just to make sure that all categories are created
        time.sleep(3)
        assign_parents(cat_parents)
        create_category_analytics_bulk(cat_analytics)

        print(f"createAndUpdateCategories: {len(new_categories)} new categories created")

        print("createAndUpdateCategories finished")
        print(f"createAndUpdateCategories took {time.time() - start_time} seconds")
    except Exception as e:
        print(f"Error in createAndUpdateCategories: {e}")
        return None
