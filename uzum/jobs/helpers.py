import random


def get_random_user_agent():
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/93.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:93.0) Gecko/20100101 Firefox/93.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/94.0.992.31",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36",
        "Mozilla/5.0 (Linux; Android 11; SM-A526B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPad; CPU OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Mobile Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:93.0) Gecko/20100101 Firefox/93.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:93.0) Gecko/20100101 Firefox/93.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/94.0.992.31 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36 Edg/94.0.992.31",
        "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 11; SM-N981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 11; SM-F926B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 11; LM-V600) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 11; LG-VELVET) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Mobile Safari/537.36",
    ]

    return random.choice(USER_AGENTS)


def generateUUID():
    uuid = ""
    chars = "0123456789abcdef"
    for i in range(32):
        uuid += chars[random.randint(0, 15)]
        if i == 7 or i == 11 or i == 15 or i == 19:
            uuid += "-"
    return uuid


def getReviewsUrl(productId: str, pageSize: int, page: int) -> str:
    return f"https://api.uzum.uz/api/product/{int(productId)}/reviews?amount={pageSize}&page={page}"


def products_payload(
    offset: int, limit: int, categoryId: str, showAdultContent: str = "TRUE", is_ru: bool = False
) -> dict:
    return {
        "operationName": "getMakeSearch",
        "query": "query getMakeSearch( $queryInput: MakeSearchQueryInput!) {makeSearch(query: $queryInput) {items { catalogCard { productId } } } }"
        if not is_ru
        else "query getMakeSearch($queryInput: MakeSearchQueryInput!) { makeSearch(query: $queryInput) { items { catalogCard { ...SkuGroupCardFragment } } } } fragment SkuGroupCardFragment on SkuGroupCard { productId title characteristicValues { id value title characteristic { values { id title value } title id } } }",
        "variables": {
            "queryInput": {
                "categoryId": categoryId,
                "filters": [],
                "pagination": {"offset": offset, "limit": limit},
                "showAdultContent": showAdultContent,
                "sort": "BY_RELEVANCE_DESC",
            }
        },
    }


def products_title_ru_payload(offset: int, limit: int, categoryId: str, showAdultContent: str = "TRUE") -> dict:
    return {
        "operationName": "getMakeSearch",
        "query": "query getMakeSearch( $queryInput: MakeSearchQueryInput!) {makeSearch(query: $queryInput) {items { catalogCard { productId, title } } } }",
        "variables": {
            "queryInput": {
                "categoryId": categoryId,
                "filters": [],
                "pagination": {"offset": offset, "limit": limit},
                "showAdultContent": showAdultContent,
                "sort": "BY_RELEVANCE_DESC",
            }
        },
    }
