from uzum.jobs.helpers import get_random_user_agent

MAX_ID_COUNT = 10_000  # max number of product ids to fetch
MAX_OFFSET = 9_999  # max offset for fetching product ids
PAGE_SIZE = 100  # page size for fetching product ids
MAX_PAGE_SIZE = 100  # max page size for fetching product ids
PRODUCTIDS_CONCURRENT_REQUESTS = 30  # number of concurrent requests for fetching product ids
PRODUCT_CONCURRENT_REQUESTS_LIMIT = 25  # number of concurrent requests for fetching product details
PRODUCT_REVIEWS_SIZE = 500  # number of reviews to fetch for each product
PRODUCTS_BUFFER_SIZE = 10000  # number of products to buffer before saving to db
PRODUCTS_REQUEST_BREAK_INDEX = 10000  # number of products to fetch before sleeping for 10 seconds

CATEGORIES_URL = "https://graphql.uzum.uz/"
MAIN_PAGE_URL = "https://graphql.uzum.uz/"
PRODUCT_URL = "https://api.uzum.uz/api/v2/product/"
PRODUCTS_URL = "https://graphql.uzum.uz/"
SELLER_URL = "https://api.uzum.uz/api/shop/"
REVIEWS_URL = "https://api.uzum.uz/api/product/253574/reviews"  # ?amount=10&page=0&hasPhoto=false


CATEGORIES_HEADER = {
    "Access-Control-Allow-Credentials": "true",
    "Authorization": "Basic YjJjLWZyb250OmNsaWVudFNlY3JldA==",
    "Origin": "https://uzum.uz",
    "Authority": "graphql.uzum.uz",
    "Referrer": "https://uzum.uz/",
    "apollographql-client-name": "web-customers",
    "apollographql-client-version": "1.5.6",
    "User-Agent": get_random_user_agent(),
    "x-iid": "25dc2cba-2d8e-4192-bac7-8f0df42cbdd5",
}


CATEGORIES_HEADER_RU = {
    "Access-Control-Allow-Credentials": "true",
    "Authorization": "Basic YjJjLWZyb250OmNsaWVudFNlY3JldA==",
    "Origin": "https://uzum.uz",
    "Authority": "graphql.uzum.uz",
    "Accept-Language": "ru-RU",
    "Referrer": "https://uzum.uz/",
    "apollographql-client-name": "web-customers",
    "apollographql-client-version": "1.5.6",
    "User-Agent": get_random_user_agent(),
    "x-iid": "25dc2cba-2d8e-4192-bac7-8f0df42cbdd5",
}


PRODUCT_HEADER = {
    "Access-Control-Allow-Credentials": "true",
    "Origin": "https://uzum.uz",
    "Authority": "api.uzum.uz",
    "Content-Type": "application/json",
    "User-Agent": get_random_user_agent(),
    "Referrer": "https://uzum.uz/",
    "Access-Control-Allow-Origin": "https://uzum.uz",
    "x-iid": "25dc2cba-2d8e-4192-bac7-8f0df42cbdd5",
}


SELLER_HEADERS = {
    "Access-Control-Allow-Credentials": "true",
    "Origin": "https://uzum.uz",
    "Authority": "api.uzum.uz",
    "Content-Type": "application/json",
    "User-Agent": get_random_user_agent(),
    "Referrer": "https://uzum.uz/",
    "Access-Control-Allow-Origin": "https://uzum.uz",
    "Accepting-Language": "uz-UZ",
    "Authorization": "Basic YjJjLWZyb250OmNsaWVudFNlY3JldA==",
    "x-iid": "25dc2cba-2d8e-4192-bac7-8f0df42cbdd5",
}

MAIN_PAGE_PAYLOAD = {
    "operationName": "getMainContent",
    "query": "query getMainContent($type: DisplayType!, $page: Int!, $size: Int!, $offerSize: Int!, $offset: Int!, $rowWidth: Int!) {\n  main {\n    content(type: $type) {\n      __typename\n      ... on BannerBlock {\n        content {\n          link\n          image {\n            high\n            __typename\n          }\n          description\n          id\n          __typename\n        }\n        __typename\n      }\n      ... on ExtendableOffer {\n        ...ExtendableOfferFragment\n        __typename\n      }\n      ... on ImageOffer {\n        image {\n          high\n          __typename\n        }\n        title\n        category {\n          id\n          title\n          __typename\n        }\n        products(page: 0, size: $offerSize) {\n          ...CatalogCardFragment\n          __typename\n        }\n        __typename\n      }\n      ... on CarouselOffer {\n        description\n        title\n        category {\n          id\n          title\n          __typename\n        }\n        products(page: 0, size: $offerSize) {\n          ...CatalogCardFragment\n          __typename\n        }\n        __typename\n      }\n      ... on InlineBanner {\n        ...InlineBannerFragment\n        __typename\n      }\n      ... on VerticalOfferBlock {\n        content {\n          ...VerticalOfferFragment\n          __typename\n        }\n        __typename\n      }\n    }\n    __typename\n  }\n}\n\nfragment InlineBannerFragment on InlineBanner {\n  description\n  image {\n    high\n    __typename\n  }\n  link\n  id\n  __typename\n}\n\nfragment CatalogCardFragment on CatalogCard {\n  ...DefaultCardFragment\n  photos {\n    key\n    link(trans: PRODUCT_540) {\n      high\n      low\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment DefaultCardFragment on CatalogCard {\n  adult\n  favorite\n  feedbackQuantity\n  id\n  minFullPrice\n  minSellPrice\n  offer {\n    due\n    icon\n    text\n    textColor\n    __typename\n  }\n  badges {\n    backgroundColor\n    text\n    textColor\n    __typename\n  }\n  ordersQuantity\n  productId\n  rating\n  title\n  __typename\n}\n\nfragment VerticalOfferFragment on VerticalOffer {\n  id\n  title\n  category {\n    id\n    __typename\n  }\n  content(offset: $offset, rowWidth: $rowWidth) {\n    ... on CardBlock {\n      content {\n        ...CatalogCardFragment\n        __typename\n      }\n      __typename\n    }\n    ... on CarouselOffer {\n      title\n      category {\n        id\n        title\n        __typename\n      }\n      products(page: 0, size: $offerSize) {\n        ...CatalogCardFragment\n        __typename\n      }\n      __typename\n    }\n    ... on ImageOffer {\n      image {\n        high\n        __typename\n      }\n      title\n      category {\n        id\n        title\n        __typename\n      }\n      products(page: 0, size: $offerSize) {\n        ...CatalogCardFragment\n        __typename\n      }\n      __typename\n    }\n    ... on InlineBanner {\n      ...InlineBannerFragment\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment ExtendableOfferFragment on ExtendableOffer {\n  description\n  id\n  products(page: $page, size: $size) {\n    ...CatalogCardFragment\n    __typename\n  }\n  title\n  category {\n    title\n    id\n    __typename\n  }\n  __typename\n}",
    "variables": {
        "offerSize": 100,
        "offset": 0,
        "page": 0,
        "rowWidth": 10,
        "size": 100,
        "type": "DESKTOP",
    },
}

CATEGORIES_PAYLOAD = {
    "operationName": "getMakeSearch",
    "query": "query getMakeSearch($queryInput: MakeSearchQueryInput!) {\n  makeSearch(query: $queryInput) {\n    id\n  queryId\n    queryText\n    category {\n      ...CategoryShortFragment\n      __typename\n    }\n    categoryTree {\n      category {\n        ...CategoryFragment\n        __typename\n      }\n      total\n      __typename\n    }\n    items {\n      catalogCard {\n        __typename\n        ...SkuGroupCardFragment\n      }\n      __typename\n    }\n    facets {\n      ...FacetFragment\n      __typename\n    }\n    total\n    mayHaveAdultContent\n    categoryFullMatch\n    offerCategory {\n      title\n      id\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment FacetFragment on Facet {\n  filter {\n    id\n    title\n    type\n    measurementUnit\n    description\n    __typename\n  }\n  buckets {\n    filterValue {\n      id\n      description\n      image\n      name\n      __typename\n    }\n    total\n    __typename\n  }\n  range {\n    min\n    max\n    __typename\n  }\n  __typename\n}\n\nfragment CategoryFragment on Category {\n  id\n  icon\n  parent {\n    id\n    __typename\n  }\n  seo {\n    header\n    metaTag\n    __typename\n  }\n  title\n  adult\n  __typename\n}\n\nfragment CategoryShortFragment on Category {\n  id\n  parent {\n    id\n    title\n    __typename\n  }\n  title\n  __typename\n}\n\nfragment SkuGroupCardFragment on SkuGroupCard {\n  ...DefaultCardFragment\n  photos {\n    key\n    link(trans: PRODUCT_540) {\n      high\n      low\n      __typename\n    }\n    previewLink: link(trans: PRODUCT_240) {\n      high\n      low\n      __typename\n    }\n    __typename\n  }\n  badges {\n    ... on BottomTextBadge {\n      backgroundColor\n      description\n      id\n      link\n      text\n      textColor\n      __typename\n    }\n    ... on UzumInstallmentTitleBadge {\n      backgroundColor\n      text\n      id\n      textColor\n      __typename\n    }\n    __typename\n  }\n  characteristicValues {\n    id\n    value\n    title\n    characteristic {\n      values {\n        id\n        title\n        value\n        __typename\n      }\n      title\n      id\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment DefaultCardFragment on CatalogCard {\n  adult\n  favorite\n  feedbackQuantity\n  id\n  minFullPrice\n  minSellPrice\n  offer {\n    due\n    icon\n    text\n    textColor\n    __typename\n  }\n  badges {\n    backgroundColor\n    text\n    textColor\n    __typename\n  }\n  ordersQuantity\n  productId\n  rating\n  title\n  __typename\n}",
    "variables": {
        "queryInput": {
            "categoryId": "1",
            "filters": [],
            "pagination": {
                "offset": 0,
                "limit": 0,
            },
            "showAdultContent": "TRUE",
            "sort": "BY_RELEVANCE_DESC",
        },
    },
}


POPULAR_SEARCHES_PAYLOAD = {
    "operationName": "Suggestions",
    "query": "query Suggestions($GetSuggestionsInput: GetSuggestionsInput!) {\n  getSuggestions(query: $GetSuggestionsInput) {\n    blocks {\n      ... on TextSuggestionsBlock {\n        values\n        __typename\n      }\n      ... on PopularSuggestionsBlock {\n        popularSuggestions\n        __typename\n      }\n      ... on CatalogCardSuggestionsBlock {\n        cards {\n          ... on ProductCard {\n            title\n            minFullPrice\n            minSellPrice\n            productId\n            photos {\n              original {\n                low\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      ... on CategorySuggestionsBlock {\n        categories {\n          title\n          id\n          icon\n          parent {\n            id\n            title\n            __typename\n          }\n          seo {\n            metaTag\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      ... on ShopSuggestionsBlock {\n        shops {\n          id\n          title\n          url\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}",
    "variables": {
        "GetSuggestionsInput": {
            "catalogCardSuggestionsLimit": 20,
            "categorySuggestionsLimit": 20,
            "popularSuggestionsLimit": 20,
            "shopSuggestionsLimit": 20,
            "text": "",
            "textSuggestionsLimit": 20,
        }
    },
}
