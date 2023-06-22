import json
import traceback
from datetime import date, datetime, timedelta
import pandas as pd
import pytz
from drf_spectacular.utils import extend_schema
import requests
import asyncio
import httpx
from collections import Counter
from asgiref.sync import async_to_sync

# from sklearn.feature_extraction.text import TfidfVectorizer
# from sklearn.metrics.pairwise import linear_kernel
from django.db.models import Avg, OuterRef, Subquery, Count, Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from uzum.category.models import Category
from uzum.jobs.constants import CATEGORIES_HEADER, POPULAR_SEARCHES_PAYLOAD, PRODUCT_HEADER
from uzum.jobs.helpers import generateUUID, get_random_user_agent
from uzum.product.models import Product, ProductAnalytics, get_today_pretty
from uzum.product.pagination import ExamplePagination
from uzum.product.serializers import ExtendedProductAnalyticsSerializer, ExtendedProductSerializer, ProductSerializer
from uzum.review.models import PopularSeaches
from uzum.sku.models import Sku, SkuAnalytics, get_day_before_pretty


class ProductsSegmentationView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request):
        try:
            max_price = request.query_params.get("max_price", None)
            if max_price is not None:
                max_price = float(max_price)
            else:
                max_price = 1000000000
            min_price = request.query_params.get("min_price", None)
            if min_price is not None:
                min_price = float(min_price)
            else:
                min_price = 0

            start_date_str = request.query_params.get("start_date", None)
            if start_date_str is None:
                date_pretty = datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")
            else:
                date_pretty = start_date_str

            segments_count = int(request.query_params.get("segments_count", 20))
            sku_analytics = SkuAnalytics.objects.filter(
                date_pretty=date_pretty, purchase_price__gte=min_price, purchase_price__lte=max_price
            )

            if not sku_analytics.exists():
                date_pretty = get_day_before_pretty(date_pretty)
                sku_analytics = SkuAnalytics.objects.filter(
                    date_pretty=date_pretty, purchase_price__gte=min_price, purchase_price__lte=max_price
                )

            if not sku_analytics.exists():
                return Response({"error": "No data for today and yesterday"}, status=status.HTTP_404_NOT_FOUND)

            # product_analytics = ProductAnalytics.objects.filter(date_pretty=date_pretty).only(
            #     "product__product_id", "orders_amount"
            # )

            purchase_prices = sku_analytics.values("sku__product__product_id").annotate(
                avg_purchase_price=Avg("purchase_price"),
                orders_amount=Subquery(
                    ProductAnalytics.objects.filter(
                        product__product_id=OuterRef("sku__product__product_id"), date_pretty=date_pretty
                    ).values("orders_amount")[:1]
                ),
            )

            # Create a DataFrame from queryset
            df = pd.DataFrame(purchase_prices)

            # Generate bins with pandas qcut
            df["segment"], bins = pd.qcut(
                df["avg_purchase_price"], segments_count, labels=False, retbins=True, duplicates="drop"
            )

            # Count number of products in each segment
            segment_counts = df.groupby("segment")["sku__product__product_id"].count().sort_index()

            # Calculate total number of orders for each segment
            segment_orders = df.groupby("segment")["orders_amount"].sum().sort_index()

            # Generate response data
            response_data = [
                {
                    "segment": i,
                    "min": bins[i],
                    "max": bins[i + 1],
                    "count": segment_counts[i],
                    "orders": segment_orders[i],
                }
                for i in range(len(bins) - 1)
            ]

            total = 0

            for i in range(len(response_data)):
                total += response_data[i]["orders"]

            return Response({"data": response_data}, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    pagination_class = ExamplePagination
    serializer_class = ExtendedProductSerializer

    @extend_schema(tags=["Product"])
    def get(self, request: Request):
        try:
            latest_analytics = ProductAnalytics.objects.filter(product=OuterRef("pk")).order_by("-created_at")

            latest_sku_analytics = SkuAnalytics.objects.filter(
                sku__product=OuterRef("pk"),
                date_pretty=Subquery(
                    SkuAnalytics.objects.filter(sku__product=OuterRef("sku__product"))
                    .order_by("-created_at")
                    .values("date_pretty")[:1]
                ),
            )

            min_price = latest_sku_analytics.order_by("purchase_price").values("purchase_price")[:1]
            max_price = latest_sku_analytics.order_by("-purchase_price").values("purchase_price")[:1]

            products = Product.objects.annotate(
                skus_count=Count("skus"),
                orders_amount=Subquery(latest_analytics.values("orders_amount")[:1]),
                reviews_amount=Subquery(latest_analytics.values("reviews_amount")[:1]),
                rating=Subquery(latest_analytics.values("rating")[:1]),
                available_amount=Subquery(latest_analytics.values("available_amount")[:1]),
                position=Subquery(latest_analytics.values("position")[:1]),
                score=Subquery(latest_analytics.values("score")[:1]),
                min_price=Subquery(min_price),
                max_price=Subquery(max_price),
            ).order_by("-created_at")

            paginator = ExamplePagination()

            page = paginator.paginate_queryset(products, request)

            serializer = self.serializer_class(page, many=True)

            return paginator.get_paginated_response(serializer.data)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    # pagination_class = ExamplePagination
    # serializer_class = ExtendedProductSerializer

    @extend_schema(tags=["Product"])
    def get(self, request: Request, product_id: str):
        try:
            start_date_str = request.query_params.get("start_date", None)

            if not start_date_str:
                # set to the 00:00 of 30 days ago in Asia/Tashkent timezone
                start_date = timezone.make_aware(
                    datetime.combine(date.today() - timedelta(days=30), datetime.min.time()),
                    timezone=pytz.timezone("Asia/Tashkent"),
                )
            else:
                start_date = timezone.make_aware(
                    datetime.combine(datetime.strptime(start_date_str, "%Y-%m-%d"), datetime.min.time()),
                    timezone=pytz.timezone("Asia/Tashkent"),
                )

            product_analytics_qs = ProductAnalytics.objects.filter(
                product__product_id=product_id, created_at__gte=start_date
            ).order_by("created_at")

            sku_analytics_qs = SkuAnalytics.objects.filter(
                sku__product__product_id=product_id, created_at__gte=start_date
            ).order_by("created_at")

            product = (
                Product.objects.filter(product_id=product_id)
                .annotate(
                    skus_count=Count("skus"),
                )
                .prefetch_related(
                    Prefetch("analytics", queryset=product_analytics_qs, to_attr="recent_analytics"),
                    Prefetch("skus__analytics", queryset=sku_analytics_qs, to_attr="recent_analytics"),
                )
                .first()
            )

            if not product:
                return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

            # Now, for each product in `products`, you can access `product.recent_analytics`
            # and `sku.recent_sku_analytics`
            # for each SKU in `product.skus.all()`, to get the analytics records since the start date.

            serializer = ExtendedProductAnalyticsSerializer(product)

            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SimilarProductsViewByUzum(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination
    serializer_class = ExtendedProductSerializer

    @staticmethod
    def fetch_similar_products_from_uzum(product_id: str):
        try:
            response = requests.get(
                "https://api.uzum.uz/api/v2/product/254379/similar?size=200",
                headers={
                    **PRODUCT_HEADER,
                    "User-Agent": get_random_user_agent(),
                    "x-iid": generateUUID(),
                },
                timeout=60,  # 60 seconds
            )

            if response.status_code == 200:
                # extract product ids
                productIds = [product["productId"] for product in response.json()]
                return productIds
            else:
                return []

        except Exception as e:
            traceback.print_exc()
            return None

    @extend_schema(tags=["Product"])
    def get(self, request: Request, product_id: str):
        try:
            productIds = SimilarProductsViewByUzum.fetch_similar_products_from_uzum(product_id)

            products = Product.objects.filter(product_id__in=productIds)

            latest_analytics = ProductAnalytics.objects.filter(product=OuterRef("pk")).order_by("-created_at")

            latest_sku_analytics = SkuAnalytics.objects.filter(
                sku__product=OuterRef("pk"),
                date_pretty=Subquery(
                    SkuAnalytics.objects.filter(sku__product=OuterRef("sku__product"))
                    .order_by("-created_at")
                    .values("date_pretty")[:1]
                ),
            )

            min_price = latest_sku_analytics.order_by("purchase_price").values("purchase_price")[:1]
            max_price = latest_sku_analytics.order_by("-purchase_price").values("purchase_price")[:1]

            products = products.annotate(
                skus_count=Count("skus"),
                orders_amount=Subquery(latest_analytics.values("orders_amount")[:1]),
                reviews_amount=Subquery(latest_analytics.values("reviews_amount")[:1]),
                rating=Subquery(latest_analytics.values("rating")[:1]),
                available_amount=Subquery(latest_analytics.values("available_amount")[:1]),
                position=Subquery(latest_analytics.values("position")[:1]),
                score=Subquery(latest_analytics.values("score")[:1]),
                min_price=Subquery(min_price),
                max_price=Subquery(max_price),
            ).order_by("-created_at")

            serializer = self.serializer_class(products, many=True)

            return Response(serializer.data, status=status.HTTP_200_OK)

        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# class SimilarProductsViewByContent(APIView):
#     permission_classes = [IsAuthenticated]
#     authentication_classes = [TokenAuthentication]
#     allowed_methods = ["GET"]
#     pagination_class = PageNumberPagination
#     serializer_class = ProductSerializer

#     @extend_schema(tags=["Product"])
#     def get(self, request: Request, product_id: str):
#         try:
#             # get all products in the same category
#             product = Product.objects.get(product_id=product_id)

#             category: Category = product.category
#             print(category)

#             parent = category.parent

#             if not parent:
#                 print("Category has no parent")
#                 parent = category

#             categories = Category.get_descendants(parent, include_self=True)
#             # print(categories)
#             # exclude the currect product's category
#             categories = [c for c in categories if c.categoryId != category.categoryId]

#             all_products = Product.objects.filter(category__in=categories)

#             # include the current product to the queryset because we excluded its category
#             # currently it is not in the queryset
#             all_products = all_products | Product.objects.filter(product_id=product_id)

#             all_products_df = pd.DataFrame.from_records(all_products.values())

#             # Load stop words from JSON file
#             with open("uzum/product/uz_stopwords.json", "r") as f:
#                 stopwords = json.load(f)

#             # Preprocessing: Combine title and description and fill any null values with an empty string
#             all_products_df["content"] = all_products_df["title"] + " " + all_products_df["description"].fillna("")

#             # Vectorize the text
#             vectorizer = TfidfVectorizer(stop_words=[])  # assuming the text is in Uzbek
#             tfidf_matrix = vectorizer.fit_transform(all_products_df["content"])

#             # Compute cosine similarity
#             cosine_sim = linear_kernel(tfidf_matrix, tfidf_matrix)

#             # Get the index of the product that matches the product_id
#             indices = pd.Series(all_products_df.index, index=all_products_df["product_id"]).drop_duplicates()
#             idx = indices[product_id]

#             # Get the pairwsie similarity scores of all products with the given product
#             sim_scores = list(enumerate(cosine_sim[idx]))

#             # Define a similarity threshold
#             similarity_threshold = 0.1  # adjust as needed

#             # Sort the products based on the similarity scores
#             sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)

#             # Get the scores of the 10 most similar products
#             sim_scores = [score for score in sim_scores if score[1] >= similarity_threshold]

#             # Get the product indices
#             product_indices = [i[0] for i in sim_scores]

#             # Get the top 10 most similar products
#             similar_products_df = all_products_df.iloc[product_indices]

#             similar_products = Product.objects.filter(product_id__in=similar_products_df["product_id"])

#             # exlude the current product
#             similar_products = similar_products.exclude(product_id=product_id)

#             paginators = PageNumberPagination()

#             page = paginators.paginate_queryset(similar_products, request)

#             serializer = self.serializer_class(page, many=True)

#             # serializer = self.serializer_class(similar_products, many=True)

#             return paginators.get_paginated_response(serializer.data)

#         except Product.DoesNotExist:
#             return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
#         except Exception as e:
#             print(e)
#             traceback.print_exc()
#             return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductReviews(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination
    serializer_class = ExtendedProductSerializer

    @staticmethod
    def fetch_reviews_from_uzum(product_id: str):
        try:
            response = requests.get(
                f"https://api.uzum.uz/api/product/{product_id}/reviews?amount=9999&page=0",
                headers={
                    **PRODUCT_HEADER,
                    "User-Agent": get_random_user_agent(),
                    "x-iid": generateUUID(),
                },
                timeout=60,  # 60 seconds
            )

            if response.status_code == 200:
                # extract product ids
                return response.json()["payload"]
            else:
                return []

        except Exception as e:
            traceback.print_exc()
            return None

    @extend_schema(tags=["Product"])
    def get(self, request: Request, product_id: str):
        try:
            reviews = ProductReviews.fetch_reviews_from_uzum(product_id)
            #         reviews = ProductReviews.fetch_reviews_from_uzum(product_id)

            #         if not reviews:
            #             return Response({"error": "No reviews found"}, status=status.HTTP_404_NOT_FOUND)

            #         # extract reviews
            #         reviews = [review["review"] for review in reviews]

            #         # join all reviews
            #         reviews = " ".join(reviews)

            #         # remove punctuation
            #         reviews = re.sub(r"[^\w\s]", "", reviews)

            #         # remove numbers
            #         reviews = re.sub(r"\d+", "", reviews)

            #         # remove stop words
            #         with open("uzum/product/uz_stopwords.json", "r") as f:
            #             stopwords = json.load(f)

            #         reviews = [word for word in reviews.split() if word not in stopwords]

            #         # count words
            #         word_count = Counter(reviews)

            #         # get top 10 words
            #         top_words = word_count.most_common(10)

            return Response(reviews, status=status.HTTP_200_OK)

        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PopularWords(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination
    serializer_class = ExtendedProductSerializer

    WORD_REQUESTS_COUNT = 50

    @staticmethod
    async def make_request(client=None):
        try:
            return await client.post(
                "https://graphql.uzum.uz/",
                json=POPULAR_SEARCHES_PAYLOAD,
                headers={
                    **CATEGORIES_HEADER,
                    "User-Agent": get_random_user_agent(),
                    "x-iid": generateUUID(),
                },
            )
        except Exception as e:
            print("Error in makeRequestProductIds: ", e)

    @staticmethod
    async def fetch_popular_seaches_from_uzum(words: list[str]):
        try:
            async with httpx.AsyncClient() as client:
                tasks = [
                    PopularWords.make_request(
                        client=client,
                    )
                    for _ in range(PopularWords.WORD_REQUESTS_COUNT)
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for res in results:
                    if isinstance(res, Exception):
                        print("Error in fetch_popular_seaches_from_uzum:", res)
                    else:
                        if not res:
                            continue
                        if res.status_code != 200:
                            continue
                        res_data = res.json()
                        if "errors" not in res_data:
                            words_ = res_data["data"]["getSuggestions"]["blocks"][0]["popularSuggestions"]
                            words.extend(words_)

        except Exception as e:
            traceback.print_exc()
            return None

    @extend_schema(tags=["Product"])
    def get(self, request: Request):
        try:
            words = PopularSeaches.objects.get(date_pretty=get_today_pretty()).words

            words = json.loads(words)

            return Response({"words": words, "count": len(words)}, status=status.HTTP_200_OK)
        except PopularSeaches.DoesNotExist:
            words = []
            async_to_sync(PopularWords.fetch_popular_seaches_from_uzum)(words)

            if len(words) == 0:
                return Response({"error": "No words found"}, status=status.HTTP_404_NOT_FOUND)

            # get frequency of words
            word_count = Counter(words)

            _ = PopularSeaches.objects.create(
                date_pretty=get_today_pretty(),
                words=json.dumps(word_count),
                requests_count=PopularWords.WORD_REQUESTS_COUNT,
            )

            return Response({"words": word_count, "count": len(word_count)}, status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
