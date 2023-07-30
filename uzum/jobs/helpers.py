import random


def get_random_user_agent():
    USER_AGENTS = [
        """Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.48""",
        """Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36""",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:85.0) Gecko/20100101 Firefox/85.0 Firefox/85.0",
        "Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:85.0) Gecko/20100101 Firefox/85.0",
        """Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36""",
        """Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15""",
        """Mozilla/5.0 (iPad; CPU OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1""",
        """Mozilla/5.0 (iPhone; CPU iPhone OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1""",
        """Mozilla/5.0 (Linux; Android 11; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.181 Mobile Safari/537.36""",
        """Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Brave Chrome/88.0.4324.182 Safari/537.36""",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:85.0) Gecko/20100101 Thunderbird/78.7.1",
        """Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59""",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
        """Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36""",
        """Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36""",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_2_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko",
        "Mozilla/5.0 (iPad; CPU OS 14_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/91.0.4472.80 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 11; SM-G975U1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Mobile Safari/537.36 EdgA/46.7.4.5158",
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
        else "query getMakeSearch( $queryInput: MakeSearchQueryInput!) {makeSearch(query: $queryInput) {items { catalogCard { productId, title } } } }",
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
