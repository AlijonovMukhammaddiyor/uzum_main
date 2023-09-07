import datetime
import logging
import time
import traceback
from datetime import timedelta
import pytz
import requests
import json
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.hashers import make_password
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, RedirectView, UpdateView
from drf_spectacular.utils import extend_schema
from django.db.models import OuterRef, Subquery
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt import authentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
import pandas as pd
from config.settings.base import env
from uzum.product.models import Product, ProductAnalytics
from uzum.shop.models import Shop, ShopAnalytics
from uzum.users.api.serializers import (
    CheckUserNameAndPhoneSerializer,
    CustomTokenRefreshSerializer,
    LogOutSerializer,
    PasswordRenewSerializer,
    UserLoginSerializer,
    create_referral,
    get_random_string,
    get_referred_by,
)
from uzum.users.tasks import send_to_single_user
from uzum.utils.general import Tariffs, get_next_day_pretty, get_today_pretty_fake
from django.http import FileResponse
import os


logger = logging.getLogger(__name__)
# disable twilio info logs
# twilio_logger = logging.getLogger("twilio.http_client")
# twilio_logger.setLevel(logging.WARNING)

User = get_user_model()

client = Client(env("TWILIO_ACCOUNT_SID"), env("TWILIO_AUTH_TOKEN"))
verify = client.verify.services(env("TWILIO_VERIFY_SERVICE_SID"))


# logging.getLogger("twilio").setLevel(logging.INFO)
class GoogleView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        try:
            print("request.data: ", request.data)
            payload = {"access_token": request.data.get("code")}  # validate the token
            r = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", params=payload)
            data = json.loads(r.text)

            if "error" in data:
                content = {"message": "wrong google token / this google token is already expired."}
                return Response(content)

            # create user if not exist
            try:
                user = User.objects.get(username=data["email"])
            except User.DoesNotExist:
                referral_code = get_random_string(6, data["email"], data["email"])
                referred_by_code = request.data.get("referred_by_code", None)
                if not referral_code:
                    user_query = request.data.get("user", None)
                    if user_query:
                        referred_by_code = user_query.get("referred_by_code", None)
                referred_by = None
                if referred_by_code:
                    referred_by = get_referred_by(referred_by_code)

                payment_date = (datetime.datetime.now() + datetime.timedelta(days=1)).astimezone(
                    pytz.timezone("Asia/Tashkent")
                )
                if referred_by_code == "invest":
                    payment_date = (datetime.datetime.now() + datetime.timedelta(days=7)).astimezone(
                        pytz.timezone("Asia/Tashkent")
                    )
                if referred_by_code == "681332":
                    payment_date = (datetime.datetime.now() + datetime.timedelta(days=3)).astimezone(
                        pytz.timezone("Asia/Tashkent")
                    )
                user = User.objects.create(
                    username=data["email"],
                    email=data["email"],
                    referral_code=referral_code,
                    password=make_password(BaseUserManager().make_random_password()),
                    referred_by=referred_by,
                    payment_date=payment_date,
                )

                create_referral(referred_by, user)

            token = UserLoginSerializer.get_token(user)
            response = {}
            response["username"] = user.username
            response["access_token"] = str(token.access_token)
            response["refresh_token"] = str(token)
            response["referred_by"] = user.referred_by.referral_code if user.referred_by else None

            return Response(response)
        except Exception as e:
            print("Error in GoogleView: ", e)
            logger.error(traceback.format_exc())
            traceback.print_exc()
            return Response(status=500, data={"message": "Internal server error"})


class SetShopsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["POST"]
    http_method_names = ["post", "head", "options"]

    def post(self, request: Request):
        try:
            data = request.data
            shop_ids = data.get("links")
            if not shop_ids:
                return Response(status=400, data={"message": "Do'konlar tanlanmagan"})
            user: User = request.user

            last_updated = user.shops_updated_at
            if not last_updated:
                pass
            else:
                # check if it at least 30 days since the last update
                if timezone.now() - last_updated < timedelta(days=30):
                    return Response(
                        status=400,
                        data={"message": "Do'konlar tanlangan kundan boshlab 30 kundan so'ng yangilanishi mumkin."},
                    )

            if user.tariff == Tariffs.FREE:
                return Response(status=400, data={"message": "Do'konlarni yangilash uchun Pro paketga o'ting"})

            if user.tariff == Tariffs.BASE:
                # only 1 shop is allowed for base users
                if len(shop_ids) == 0:
                    return Response(status=400, data={"message": "Iltimos, 1 tagacha do'kon tanlang"})

                if len(shop_ids) > 1:
                    return Response(status=400, data={"message": "Iltimos, 1 tagacha do'kon tanlang"})

                shop_id = shop_ids[0]
                shop = Shop.objects.get(link=shop_id)
                # account_id = shop.account_id

                # for shop_id in shop_ids:
                #     shop = Shop.objects.get(link=shop_id)
                #     if shop.account_id != account_id:
                #         return Response(status=400, data={"message": "Do'konlar bir xisobga tegishli bo'lishi kerak"})

                shop_id = shop_ids[0]
                shop = Shop.objects.get(link=shop_id)
                user.shops.clear()
                user.shops.add(shop)

                # if len(shop_ids) == 1:
                #     shop_id = shop_ids[1]
                #     shop = Shop.objects.get(link=shop_id)
                #     user.shops.add(shop)

            elif user.tariff == Tariffs.SELLER:
                #  4 shops is allowed for proplus users
                if len(shop_ids) == 0:
                    return Response(status=400, data={"message": "Iltimos, 4 tagacha do'kon tanlang"})

                if len(shop_ids) > 4:
                    return Response(status=400, data={"message": "Iltimos, 4 tagacha do'kon tanlang"})

                shop_id = shop_ids[0]
                shop = Shop.objects.get(link=shop_id)
                # account_id = shop.account_id

                # for shop_id in shop_ids:
                #     shop = Shop.objects.get(link=shop_id)
                #     if shop.account_id != account_id:
                #         return Response(status=400, data={"message": "Do'konlar bir xisobga tegishli bo'lishi kerak"})

                user.shops.clear()

                for shop_id in shop_ids:
                    shop = Shop.objects.get(link=shop_id)
                    user.shops.add(shop)

            user.shops_updated_at = timezone.now()
            user.save()

            return Response(status=200, data={"message": "Shops successfully set"})
        except Exception as e:
            print("Error in SetShopsView: ", e)
            traceback.print_exc()
            return Response(status=500, data={"message": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."})


class AddfavouriteShopView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    BASE_LIMIT = 1
    SELLER_LIMIT = 4
    BUSINESS_LIMIT = 10

    def post(self, request: Request):
        """
        Add the shop to the user's favourite shops
        Args:
            request (Request): _description_

        Returns:
            _type_: _description_
        """
        try:
            data = request.data
            link = data.get("link")
            if not link:
                return Response(status=400, data={"message": "Do'kon tanlanmagan", "message_ru": "Магазин не выбран"})
            user: User = request.user

            if user.tariff == Tariffs.FREE:
                return Response(
                    status=400,
                    data={
                        "message": "Do'konlarni yangilash uchun Pro paketga o'ting",
                        "message_ru": "Для обновления магазинов перейдите на Pro пакет",
                    },
                )

            if user.tariff == Tariffs.BASE:
                if user.favourite_shops.all().count() >= self.BASE_LIMIT:
                    return Response(
                        status=400,
                        data={
                            "message": "Siz 1 dan ortiq do'konni tanlay olmaysiz",
                            "message_ru": "Вы не можете выбрать более 1 магазина",
                        },
                    )

            if user.tariff == Tariffs.SELLER:
                if user.favourite_shops.all().count() >= self.SELLER_LIMIT:
                    return Response(
                        status=400,
                        data={
                            "message": "Siz 4 dan ortiq do'konni tanlay olmaysiz",
                            "message_ru": "Вы не можете выбрать более 4 магазинов",
                        },
                    )

            if user.tariff == Tariffs.BUSINESS:
                if user.favourite_shops.all().count() >= self.BUSINESS_LIMIT:
                    return Response(
                        status=400,
                        data={
                            "message": "Siz 10 dan ortiq do'konni tanlay olmaysiz",
                            "message_ru": "Вы не можете выбрать более 10 магазинов",
                        },
                    )

            shop = Shop.objects.get(link=link)
            user.favourite_shops.add(shop)
            user.save()

            return Response(
                status=200,
                data={
                    "message": "Shop successfully added to favourites",
                    "message_ru": "Магазин успешно добавлен в избранное",
                },
            )
        except Exception as e:
            print("Error in AddfavouriteShopView: ", e)
            traceback.print_exc()
            return Response(
                status=500,
                data={
                    "message": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",
                    "message_ru": "Произошла ошибка. Пожалуйста, попробуйте еще раз.",
                },
            )


class RemovefavouriteShopView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request: Request):
        """
        Remove the shop from the user's favourite shops
        Args:
            request (Request): _description_

        Returns:
            _type_: _description_
        """
        try:
            data = request.data
            link = data.get("link")
            if not link:
                return Response(status=400, data={"message": "Do'kon tanlanmagan", "message_ru": "Магазин не выбран"})
            user: User = request.user

            shop = Shop.objects.get(link=link)
            user.favourite_shops.remove(shop)
            user.save()

            return Response(
                status=200,
                data={"message": "Do'kon muvaffaqiyatli o'chirildi", "message_ru": "Магазин успешно удален"},
            )
        except Exception as e:
            print("Error in RemovefavouriteShopView: ", e)
            traceback.print_exc()
            return Response(
                status=500,
                data={
                    "message": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",
                    "message_ru": "Произошла ошибка. Пожалуйста, попробуйте еще раз.",
                },
            )


from django.db import connection


class GetFavouriteShopsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request: Request):
        """
        Get the user's favourite shops along with their latest analytics using raw SQL
        Args:
            request (Request): _description_

        Returns:
            _type_: _description_
        """
        try:
            user: User = request.user
            only_links = request.GET.get("only_links", False)
            # Convert the list of shop IDs to a comma-separated string
            shop_ids = user.favourite_shops.values_list("link", flat=True)
            shop_ids_str = ",".join(map(str, shop_ids))

            if only_links:
                return Response(status=200, data={"shops": shop_ids})

            shop_ids_str = ",".join([f"'{link}'" for link in shop_ids])

            # Raw SQL query to fetch the latest analytics for each shop
            sql = f"""
            SELECT
                s.seller_id AS shop_id,
                s.title AS shop_name,
                s.link AS shop_link,
                a.total_products,
                a.total_orders,
                a.total_revenue,
                a.total_reviews,
                a.average_purchase_price,
                a.average_order_price,
                a.rating,
                a.position
            FROM shop_shop s
            LEFT JOIN (
                SELECT
                    shop_id,
                    total_products,
                    total_orders,
                    total_revenue,
                    total_reviews,
                    average_purchase_price,
                    average_order_price,
                    rating,
                    position
                FROM shop_shopanalytics
                WHERE created_at = (
                    SELECT MAX(created_at)
                    FROM shop_shopanalytics sa2
                    WHERE sa2.shop_id = shop_shopanalytics.shop_id
                )
            ) a ON s.seller_id = a.shop_id
            WHERE s.link IN ({shop_ids_str})
            """

            with connection.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()

            shops_data = [
                {
                    "shop_title": row[1] + "((" + row[2] + "))",
                    "total_products": row[3],
                    "total_orders": row[4],
                    "total_revenue": row[5],
                    "total_reviews": row[6],
                    "average_purchase_price": row[7],
                    "rating": row[9],
                    "position": row[10],
                }
                for row in rows
            ]

            return Response(status=200, data={"shops": shops_data})
        except Exception as e:
            print("Error in GetFavouriteShopsView: ", e)
            traceback.print_exc()
            return Response(status=500, data={"message": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."})


class AddfavouriteProductView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    BASE_LIMIT = 20
    SELLER_LIMIT = 50
    BUSINESS_LIMIT = 100

    def post(self, request: Request):
        """
        Add the product to the user's favourite products
        Args:
            request (Request): _description_

        Returns:
            _type_: _description_
        """
        try:
            data = request.data
            product_id = data.get("product_id")
            if not product_id:
                return Response(status=400, data={"message": "Mahsulot tanlanmagan", "message_ru": "Товар не выбран"})
            user: User = request.user

            if user.tariff == Tariffs.FREE:
                return Response(
                    status=400,
                    data={
                        "message": "Mahsulotlarni tanlash uchun boshqa paketga o'ting",
                        "message_ru": "Для выбора товаров перейдите на другой пакет",
                    },
                )

            if user.tariff == Tariffs.BASE:
                if user.favourite_products.all().count() >= self.BASE_LIMIT:
                    return Response(
                        status=400,
                        data={
                            "message": "Siz 20 dan ortiq mahsulotni tanlay olmaysiz",
                            "message_ru": "Вы не можете выбрать более 20 товаров",
                        },
                    )

            if user.tariff == Tariffs.SELLER:
                if user.favourite_products.all().count() >= self.SELLER_LIMIT:
                    return Response(
                        status=400,
                        data={
                            "message": "Siz 50 dan ortiq mahsulotni tanlay olmaysiz",
                            "message_ru": "Вы не можете выбрать более 50 товаров",
                        },
                    )

            if user.tariff == Tariffs.BUSINESS:
                if user.favourite_products.all().count() >= self.BUSINESS_LIMIT:
                    return Response(
                        status=400,
                        data={
                            "message": "Siz 100 dan ortiq mahsulotni tanlay olmaysiz",
                            "message_ru": "Вы не можете выбрать более 100 товаров",
                        },
                    )

            product = Product.objects.get(product_id=product_id)
            user.favourite_products.add(product)
            user.save()

            return Response(
                status=200, data={"message": "Mahsulot muvaffaqiyatli tanlandi", "message_ru": "Товар успешно выбран"}
            )
        except Exception as e:
            print("Error in AddfavouriteProductView: ", e)
            traceback.print_exc()
            return Response(
                status=500,
                data={
                    "message": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",
                    "message_ru": "Произошла ошибка. Пожалуйста, попробуйте еще раз.",
                },
            )


class RemovefavouriteProductView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request: Request):
        """
        Remove the product from the user's favourite products
        Args:
            request (Request): _description_

        Returns:
            _type_: _description_
        """
        try:
            data = request.data
            product_id = data.get("product_id")
            if not product_id:
                return Response(status=400, data={"message": "Mahsulot tanlanmagan", "message_ru": "Товар не выбран"})
            user: User = request.user

            product = Product.objects.get(product_id=product_id)
            user.favourite_products.remove(product)
            user.save()

            return Response(
                status=200,
                data={"message": "Mahsulot muvaffaqiyatli o'chirildi", "message_ru": "Товар успешно удален"},
            )
        except Exception as e:
            print("Error in RemovefavouriteProductView: ", e)
            traceback.print_exc()
            return Response(
                status=500,
                data={
                    "message": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",
                    "message_ru": "Произошла ошибка. Пожалуйста, попробуйте еще раз.",
                },
            )


class GetFavouriteProductsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request: Request):
        """
        Get the user's favourite products along with their latest analytics using raw SQL
        Args:
            request (Request): _description_

        Returns:
            _type_: _description_
        """
        try:
            user: User = request.user
            product_ids = user.favourite_products.values_list("product_id", flat=True)
            only_ids = request.GET.get("only_ids", False)
            # Convert the list of product IDs to a comma-separated string
            product_ids_str = ",".join(map(str, product_ids))

            if only_ids:
                return Response(status=200, data={"products": product_ids})

            # Raw SQL query to fetch the latest analytics for each product
            sql = f"""
                SELECT
                    p.product_id AS product_id,
                    p.title AS product_name,
                    p.title_ru AS product_name_ru,
                    p.photos AS product_photo,
                    c.title AS category_title,
                    c.title_ru AS category_title_ru,
                    c."categoryId" AS category_id,
                    s.title AS shop_title,
                    s.link AS link,
                    a.available_amount,
                    a.reviews_amount,
                    a.rating,
                    a.orders_amount,
                    a.orders_money,
                    a.position_in_shop,
                    a.position_in_category,
                    a.position,
                    a.average_purchase_price,
                    a.score
                FROM product_product p
                LEFT JOIN category_category c ON p.category_id = c."categoryId"
                LEFT JOIN shop_shop s ON p.shop_id = s.seller_id
                LEFT JOIN (
                    SELECT
                        product_id,
                        available_amount,
                        reviews_amount,
                        rating,
                        orders_amount,
                        orders_money,
                        position_in_shop,
                        position_in_category,
                        position,
                        average_purchase_price,
                        score
                    FROM product_productanalytics
                    WHERE created_at = (
                        SELECT MAX(created_at)
                        FROM product_productanalytics pa2
                        WHERE pa2.product_id = product_productanalytics.product_id
                    )
                ) a ON p.product_id = a.product_id
                WHERE p.product_id IN ({product_ids_str})
            """

            with connection.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()

            products_data = [
                {
                    "product_id": row[0],
                    "product_title": row[1] + "((" + str(row[0]) + "))",
                    "product_title_ru": (row[2] if row[2] else row[1]) + "((" + str(row[0]) + "))",
                    "category_title": row[3] + "((" + str(row[6]) + "))",
                    "category_title_ru": (row[4] if row[4] else row[3]) + "((" + str(row[6]) + "))",
                    "category_id": row[6],
                    "shop_title": row[7] + "((" + row[8] + "))",
                    "shop_link": row[8],
                    "available_amount": row[9],
                    "reviews_amount": row[10],
                    "rating": row[11],
                    "orders_amount": row[12],
                    "orders_money": row[13],
                    "position_in_shop": row[14],
                    "position_in_category": row[15],
                    "position": row[16],
                    "average_purchase_price": row[17],
                    "photos": row[3],
                }
                for row in rows
            ]

            return Response(status=200, data={"products": products_data})
        except Exception as e:
            print("Error in GetFavouriteProductsView: ", e)
            traceback.print_exc()
            return Response(status=500, data={"message": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."})


class VerificationSendView(APIView):
    permission_classes = [AllowAny]
    allowed_methods = ["POST"]

    @extend_schema(tags=["auth"])
    def post(self, request: Request):
        try:
            data = request.data
            phone_number = data.get("phone_number")
            is_register = data.get("is_register", False)

            if not phone_number:
                return Response(status=400, data={"message": "Phone number is required"})

            # if is_register:
            #     users = User.objects.filter(phone_number=phone_number)

            #     if users.exists():
            #         return Response(status=400, data={"message": "Phone number already exists"})
            print("phone_number: ", phone_number)
            verify.verifications.create(
                to=phone_number,
                channel="sms",
            )

            return Response(status=200, data={"message": "Verification code sent successfully"})
        except Exception as e:
            print("Error in PhoneVerificationView: ", e)

            return Response(status=500, data={"message": "Internal server error"})


class CodeVerificationView(APIView):
    permission_classes = [AllowAny]
    allowed_methods = ["POST"]

    def post(self, request: Request):
        try:
            data = request.data
            code = data.get("code")
            phone_number = data.get("phone_number")
            if not code or not phone_number:
                return Response(status=400, data={"message": "Code and phone number are required"})

            result = verify.verification_checks.create(to=phone_number, code=code)

            if result.status == "approved":
                # user = User.objects.get(phone_number=phone_number)
                # token, _ = Token.objects.get_or_create(user=user)
                # return Response(status=200, data={"token": token.key})
                response = Response(status=200, data={"message": "Code verified successfully"})
                response.set_cookie(
                    "verification_token",
                    env("VERIFICATION_TOKEN"),
                    expires=datetime.datetime.now() + timedelta(minutes=10),
                )  # Replace 'token_value' with an actual token
                return response

            return Response(status=400, data={"message": "Invalid verification code"})

        except TwilioRestException as e:
            print("Error in check: ", e)
            return Response(status=400, data={"message": "Invalid verification code"})
        except Exception as e:
            print("Error in PhoneVerificationView: ", e)
            return Response(status=500, data={"message": "Internal server error"})


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "username"
    slug_url_kwarg = "username"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["phone_number", "email", "username", "shop"]
    success_message = _("Information successfully updated")

    def get_success_url(self):
        assert self.request.user.is_authenticated  # for mypy to know that the user is authenticated
        return self.request.user.get_absolute_url()

    def get_object(self):
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self):
        return reverse("users:detail", kwargs={"username": self.request.user.username})


user_redirect_view = UserRedirectView.as_view()


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = UserLoginSerializer

    @extend_schema(tags=["token"], operation_id="login")
    def post(self, request, *args, **kwargs):
        print("request.data: ", request.data)
        serializer = self.get_serializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        response = Response(serializer.validated_data, status=200)

        return response


class CustomTokenRefreshView(TokenRefreshView):
    serializer_class = CustomTokenRefreshSerializer

    @extend_schema(tags=["token"], operation_id="refresh")
    def post(self, request, *args, **kwargs):
        # Just let the original TokenRefreshView handle the refresh
        return super().post(request, *args, **kwargs)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [authentication.JWTAuthentication]
    serializer_class = LogOutSerializer

    @extend_schema(tags=["auth"], operation_id="logout")
    def post(self, request, *args, **kwargs):
        # Logic to invalidate the tokens or clear session-related data
        # For example, you can use Django's built-in logout function:
        from django.contrib.auth import logout

        logout(request)

        # Clear the cookies
        print("Cookies cleared")
        response = Response({"detail": "Logged out"})
        response.delete_cookie("access")
        response.delete_cookie("refresh")

        return response


class CheckUserNameAndPhone(APIView):
    permission_classes = [AllowAny]
    allowed_methods = ["GET"]
    serializer_class = CheckUserNameAndPhoneSerializer

    @extend_schema(tags=["auth"], operation_id="check_username_and_phone")
    def get(self, request, *args, **kwargs):
        try:
            data = request.query_params
            phone_number = data.get("phone_number")
            username = data.get("username")
            if not phone_number or not username:
                return Response(status=400, data={"message": "Phone number and username are required"})
            print(phone_number, username)
            user = User.objects.filter(phone_number=phone_number, username=username).first()
            if user:
                return Response(status=200, data={"message": "User exists"})
            return Response(status=400, data={"message": "User does not exist"})
        except Exception as e:
            print("Error in CheckUserNameAndPhone: ", e)
            return Response(status=500, data={"message": "Internal server error"})


class PasswordRenewView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PasswordRenewSerializer

    @extend_schema(tags=["auth"], operation_id="password_renew")
    def post(self, request, *args, **kwargs):
        try:
            data = request.data
            phone_number = data.get("phone_number")
            username = data.get("username")
            password = data.get("password")

            if not phone_number or not username or not password:
                return Response(status=400, data={"message": "Phone number and username are required"})

            if len(password) < 8:
                return Response(status=400, data={"message": "Password must be at least 8 characters long"})

            user = User.objects.filter(phone_number=phone_number, username=username).first()
            if not user:
                return Response(status=400, data={"message": "User does not exist"})

            # Update the user's password
            user.set_password(password)
            user.save()

            return Response(status=200, data={"message": "New password set successfully"})

        except Exception as e:
            print("Error in PasswordRenewView: ", e)
            return Response(status=500, data={"message": "Internal server error"})


class TelegramBotView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def send_message(self, chat_id, text):
        send_message_url = "https://api.telegram.org/bot6419033506:AAETG8prNWtydbqFEdiiFa-z_YxRaRSbzA8/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        requests.post(send_message_url, data=payload)

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            message = data.get("message", {})
            text = message.get("text", "")
            chat_id = message.get("chat", {}).get("id")

            # User starts the bot
            if text == "/start":
                self.send_message(chat_id, "Укажите свой уникальный токен для привязки вашей учетной записи.")
                return Response(status=200, data={"status": "ok"})

            user = User.objects.get(telegram_chat_id=chat_id)

            if text != "/request":
                # Check if the text is a valid token in your database
                try:
                    user = User.objects.get(telegram_chat_id=chat_id)
                    if user.tariff == Tariffs.FREE or user.tariff == Tariffs.TRIAL:
                        self.send_message(chat_id, "Ваш тарифный план не позволяет использовать эту функцию.")
                    else:
                        # If the user's telegram_chat_id is already set, inform them
                        if user.telegram_chat_id:
                            self.send_message(chat_id, "Ваш аккаунт уже привязан!")
                        else:
                            user.telegram_chat_id = chat_id
                            user.is_telegram_connected = True
                            user.save()
                            self.send_message(chat_id, "Ваш аккаунт успешно привязан!")

                except User.DoesNotExist:
                    self.send_message(chat_id, "Invalid token. Please try again.")

            if text == "/request":
                if user.tariff == Tariffs.FREE or user.tariff == Tariffs.TRIAL:
                    self.send_message(chat_id, "Ваш тарифный план не позволяет использовать эту функцию....")
                else:
                    # first check if the user is registered, if not - inform them
                    # if they are registered, send the report
                    try:
                        user = User.objects.get(telegram_chat_id=chat_id)
                        self.send_message(chat_id, "Ваш отчет готовится. Пожалуйста, подождите немного.")
                        send_to_single_user(user)
                    except User.DoesNotExist:
                        self.send_message(
                            chat_id,
                            "Вы не подключились к боту Telegram с помощью предоставленного нами уникального токена.",
                        )

            return Response(status=200, data={"status": "ok"})
        except User.DoesNotExist as e:
            return Response(
                status=200,
                data={
                    "message": "Вы не подключились к боту Telegram с помощью предоставленного нами уникального токена."
                },
            )

        except Exception as e:
            print("Error in TelegramConnectView: ", e)
            traceback.print_exc()
            return Response(status=500, data={"message": "Произошла ошибка"})
