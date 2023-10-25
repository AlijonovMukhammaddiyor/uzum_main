import time
import traceback
from datetime import datetime

import pytz
import requests
from django.db import transaction
from django.db.models import Case, Value, When

from uzum.category.models import Category, CategoryAnalytics
from uzum.jobs.constants import (CATEGORIES_HEADER, CATEGORIES_HEADER_RU,
                                 CATEGORIES_PAYLOAD, CATEGORIES_URL)
from uzum.jobs.helpers import generateUUID, get_random_user_agent


import cloudscraper

# Assuming other required imports and constants are defined above

def get_categories_tree():
    # URLs and proxy information (update with actual values).
    PROXY = "https://85.112.193.37:8080"  # Replace with your actual proxy

    # You might want to externalize these settings or pass them as function parameters.
    MAX_RETRIES = 10
    RETRY_DELAY = 1  # Delay in seconds between retries

    for attempt in range(MAX_RETRIES):
        try:
            # Create a new scraper instance, configuring the desired proxy.
            scraper = cloudscraper.create_scraper(
                browser={
                    "browser": "chrome",
                    "platform": "windows",
                    "mobile": False,
                }
            )

            # Making the POST request.
            response = scraper.post(
                CATEGORIES_URL,
                json=CATEGORIES_PAYLOAD,
                headers={
                    **CATEGORIES_HEADER,
                    "User-Agent": scraper.headers["User-Agent"],
                    "Content-Type": "application/json",
                },
                proxies={
                    "http": PROXY,
                    "https": PROXY,
                }
            )

            # Successful response
            if response.status_code == 200:
                json_response = response.json()
                # Validate the response structure before attempting to access fields.
                if 'data' in json_response and 'makeSearch' in json_response['data'] and 'categoryTree' in json_response['data']['makeSearch']:
                    return json_response['data']['makeSearch']['categoryTree']
                else:
                    raise ValueError("Unexpected JSON structure.")

            # Log non-success statuses.
            else:
                print(f"Attempt {attempt+1} failed with status code: {response.status_code} - {response.text}")
                time.sleep(RETRY_DELAY)  # Delay before the next attempt.

        except cloudscraper.exceptions.CloudflareChallengeError as e:
            print(f"Cloudflare challenge error on attempt {attempt+1}: {e}")
            traceback.print_exc()
            time.sleep(RETRY_DELAY)

        except Exception as e:
            # You may want to distinguish between fatal errors and retryable errors.
            print(f"An error occurred on attempt {attempt+1}: {e}")
            traceback.print_exc()
            time.sleep(RETRY_DELAY)

    # All attempts failed; return None to indicate an unsuccessful operation.
    print("All attempts failed. Returning None.")
    return None

def get_categories_tree_ru():
    try:
        tree = requests.post(
            CATEGORIES_URL,
            json=CATEGORIES_PAYLOAD,
            headers={
                **CATEGORIES_HEADER_RU,
                "User-Agent": get_random_user_agent(),
                "x-iid": generateUUID(),
                "Content-Type": "application/json",
            },
        )
        if tree.status_code == 200:
            return tree.json().get("data").get("makeSearch").get("categoryTree")
        else:
            print(f"Error in get_categories_tree: {tree.status_code} - {tree.text}")
            return None

    except Exception as e:
        print("Error in get_categories_tree: ", e)
        traceback.print_exc()
        return None


def add_russian_titles():
    try:
        tree = get_categories_tree_ru()
        res = {}
        for i, category in enumerate(tree):
            res[category["category"]["id"]] = category["category"]["title"]

        whens = [When(categoryId=k, then=Value(v)) for k, v in res.items()]

        # print(whens)

        with transaction.atomic():
            Category.objects.filter(categoryId__in=res.keys()).update(title_ru=Case(*whens))

    except Exception as e:
        print("Error in add_russian_titles: ", e)
        traceback.print_exc()
        return None


def prepare_categories_for_bulk_create(
    tree,
    cat_analytics: list[CategoryAnalytics],
    new_cats: list[Category],
    cat_parents: list[tuple[int, int]],
):
    try:
        current_categories = Category.objects.all().order_by("categoryId")
        # make dict of all categories: key - categoryId, value - anything
        categories_dict = {category.categoryId: category for category in current_categories}

        for i, category in enumerate(tree):
            cat_analytics.append(
                CategoryAnalytics(
                    total_products=category["total"],
                    category_id=int(category["category"]["id"]),
                    created_at=datetime.now(tz=pytz.timezone("Asia/Tashkent")),
                ),
            )
            current_id = category["category"]["id"]

            if category["category"]["id"] in categories_dict:
                if current_id == 1:
                    continue
                # in case, existing category does not have parent, assign it
                parent = categories_dict[category["category"]["id"]].parent

                if not parent:
                    # assign parent once all new categories are created
                    # cat_parents[current_id] = category["category"]["parent"]["id"]
                    cat_parents.append((current_id, category["category"]["parent"]["id"]))

                    if current_id == category["category"]["parent"]["id"]:
                        raise Exception("Category cannot be its own parent")
                        return None
                elif parent.categoryId != category["category"]["parent"]["id"]:
                    # if parent changed
                    print(f"{category['category']['id']} - {parent.categoryId} parent changed")
                    cat_parents.append((current_id, category["category"]["parent"]["id"]))

            else:
                new_cats.append(
                    Category(
                        categoryId=category["category"]["id"],
                        title=category["category"]["title"],
                        seo=category["category"]["seo"]["header"],
                        adult=category["category"]["adult"],
                    )
                )
                if category["category"]["parent"]:
                    # assign parents once all new categories are created
                    # cat_parents[current_id] = category["category"]["parent"]["id"]
                    cat_parents.append((current_id, category["category"]["parent"]["id"]))

                    if current_id == category["category"]["parent"]["id"]:
                        raise Exception("Category cannot be its own parent.1")
                        return None

    except Exception as e:
        print(f"Error in prepare_categories_for_bulk_create: {e}")
        traceback.print_exc()
        return None


def assign_parents(new_cat_parents: list[tuple[int, int]]):
    try:
        # find both new category and parent category
        for new_cat_id, parent_cat_id in new_cat_parents:
            new_cat = Category.objects.get(categoryId=new_cat_id)
            parent_cat = Category.objects.get(categoryId=parent_cat_id)

            # assign parent category to new category
            new_cat.parent = parent_cat
            new_cat.save()

            if parent_cat.title == "Pechlar":
                print(f"{new_cat.title} - {parent_cat.title}")

    except Exception as e:
        print(f"Error in assign_parents: {e}")
        return None
