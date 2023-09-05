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
            shop_id = data.get("shop_id")
            if not shop_id:
                return Response(status=400, data={"message": "Do'kon tanlanmagan"})
            user: User = request.user

            if user.tariff == Tariffs.FREE:
                return Response(status=400, data={"message": "Do'konlarni yangilash uchun Pro paketga o'ting"})

            if user.tariff == Tariffs.BASE:
                if user.favourite_shops.all().count() >= self.BASE_LIMIT:
                    return Response(status=400, data={"message": "Siz 1 dan ortiq do'konni tanlay olmaysiz"})

            if user.tariff == Tariffs.SELLER:
                if user.favourite_shops.all().count() >= self.SELLER_LIMIT:
                    return Response(status=400, data={"message": "Siz 4 dan ortiq do'konni tanlay olmaysiz"})

            if user.tariff == Tariffs.BUSINESS:
                if user.favourite_shops.all().count() >= self.BUSINESS_LIMIT:
                    return Response(status=400, data={"message": "Siz 10 dan ortiq do'konni tanlay olmaysiz"})

            shop = Shop.objects.get(seller_id=shop_id)
            user.favourite_shops.add(shop)
            user.save()

            return Response(status=200, data={"message": "Shop successfully added to favourites"})
        except Exception as e:
            print("Error in AddfavouriteShopView: ", e)
            traceback.print_exc()
            return Response(status=500, data={"message": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."})


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
            shop_id = data.get("shop_id")
            if not shop_id:
                return Response(status=400, data={"message": "Do'kon tanlanmagan"})
            user: User = request.user

            shop = Shop.objects.get(seller_id=shop_id)
            user.favourite_shops.remove(shop)
            user.save()

            return Response(status=200, data={"message": "Shop successfully removed from favourites"})
        except Exception as e:
            print("Error in RemovefavouriteShopView: ", e)
            traceback.print_exc()
            return Response(status=500, data={"message": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."})


class GetFavouriteShopsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request: Request):
        """
        Get the user's favourite shops
        Args:
            request (Request): _description_

        Returns:
            _type_: _description_
        """
        try:
            user: User = request.user
            shops = user.favourite_shops.all()
            shops = [{"id": shop.seller_id, "name": shop.title} for shop in shops]
            return Response(status=200, data={"shops": shops})
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
                return Response(status=400, data={"message": "Mahsulot tanlanmagan"})
            user: User = request.user

            if user.tariff == Tariffs.FREE:
                return Response(status=400, data={"message": "Mahsulotlarni yangilash uchun Pro paketga o'ting"})

            if user.tariff == Tariffs.BASE:
                if user.favourite_products.all().count() >= self.BASE_LIMIT:
                    return Response(status=400, data={"message": "Siz 20 dan ortiq mahsulotni tanlay olmaysiz"})

            if user.tariff == Tariffs.SELLER:
                if user.favourite_products.all().count() >= self.SELLER_LIMIT:
                    return Response(status=400, data={"message": "Siz 50 dan ortiq mahsulotni tanlay olmaysiz"})

            if user.tariff == Tariffs.BUSINESS:
                if user.favourite_products.all().count() >= self.BUSINESS_LIMIT:
                    return Response(status=400, data={"message": "Siz 100 dan ortiq mahsulotni tanlay olmaysiz"})

            product = Product.objects.get(product_id=product_id)
            user.favourite_products.add(product)
            user.save()

            return Response(status=200, data={"message": "Product successfully added to favourites"})
        except Exception as e:
            print("Error in AddfavouriteProductView: ", e)
            traceback.print_exc()
            return Response(status=500, data={"message": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."})


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
                return Response(status=400, data={"message": "Mahsulot tanlanmagan"})
            user: User = request.user

            product = Product.objects.get(product_id=product_id)
            user.favourite_products.remove(product)
            user.save()

            return Response(status=200, data={"message": "Product successfully removed from favourites"})
        except Exception as e:
            print("Error in RemovefavouriteProductView: ", e)
            traceback.print_exc()
            return Response(status=500, data={"message": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."})


class GetFavouriteProductsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request: Request):
        """
        Get the user's favourite products
        Args:
            request (Request): _description_

        Returns:
            _type_: _description_
        """
        try:
            user: User = request.user
            products = user.favourite_products.all()
            products = [{"id": product.product_id, "name": product.title} for product in products]
            return Response(status=200, data={"products": products})
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


class UserDailyReport(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def prepare_shop_statistics(self, request, shop):
        try:
            user: User = request.user

            print("Shop Daily Sales View")
            start = time.time()

            today_pretty = get_today_pretty_fake()
            date = request.query_params.get("date", None)

            if not date:
                date = today_pretty
            else:
                date = get_next_day_pretty(date)

            start_date = timezone.make_aware(
                datetime.datetime.strptime(date, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            user: User = request.user

            # check if start date is before 30 days
            if start_date < timezone.make_aware(
                datetime.datetime.now() - timedelta(days=30), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0):
                if user.tariff == Tariffs.SELLER or user.tariff == Tariffs.BUSINESS or user.tariff == Tariffs.BASE:
                    pass
                else:
                    return None

            def calculate_diff(target, before):
                """
                Helper function to calculate the difference between the target and before value.
                """
                if target is not None and before is not None:
                    return target - before
                return target

            analytics_date = (
                ProductAnalytics.objects.filter(date_pretty=date, product__shop=shop)
                .values(
                    "average_purchase_price",
                    "orders_amount",
                    "position",
                    "position_in_category",
                    "position_in_shop",
                    "available_amount",
                    "reviews_amount",
                    "rating",
                    "product__title",
                    "product__title_ru",
                    "product__category__title",
                    "product__category__title_ru",
                    "product__product_id",
                    "product__category__categoryId",
                    "product__photos",
                    "date_pretty",
                )
                .order_by("-orders_amount")
            )

            latest_date_subquery = (
                ProductAnalytics.objects.filter(
                    product__shop=shop, created_at__lt=start_date, product_id=OuterRef("product_id")
                )
                .order_by("-created_at")
                .values("date_pretty")[:1]
            )

            day_before_analytics = ProductAnalytics.objects.filter(
                product__shop=shop, date_pretty=Subquery(latest_date_subquery)
            ).values(
                "average_purchase_price",
                "orders_amount",
                "position",
                "position_in_category",
                "position_in_shop",
                "available_amount",
                "reviews_amount",
                "rating",
                "product__title",
                "product__title_ru",
                "product__category__title",
                "product__category__title_ru",
                "product__product_id",
                "product__category__categoryId",
                "date_pretty",
            )

            target_analytics = list(analytics_date)

            before_analytics_dict = {i["product__product_id"]: i for i in day_before_analytics}

            for item in target_analytics:
                before_item = before_analytics_dict.get(item["product__product_id"], None)
                item["orders"] = {
                    "target": item["orders_amount"],
                    # "before": before_item["orders_amount"],
                    "before": before_item.get("orders_amount", None) if before_item else None,
                    "change": calculate_diff(item["orders_amount"], before_item["orders_amount"])
                    if before_item
                    else item["orders_amount"],
                }
                item["reviews"] = {
                    "target": item["reviews_amount"],
                    # "before": before_item["reviews_amount"],
                    "before": before_item.get("reviews_amount", None) if before_item else None,
                    "change": calculate_diff(item["reviews_amount"], before_item["reviews_amount"])
                    if before_item
                    else item["reviews_amount"],
                }

                item["rating"] = {
                    "target": item["rating"],
                    # "before": before_item["rating"],
                    "before": before_item.get("rating", None) if before_item else None,
                    "change": calculate_diff(item["rating"], before_item["rating"]) if before_item else item["rating"],
                }

                item["position"] = {
                    "target": item["position"],
                    # "before": before_item["position"],
                    "before": before_item.get("position", None) if before_item else None,
                    "change": calculate_diff(item["position"], before_item["position"])
                    if before_item
                    else item["position"],
                }

                item["position_in_category"] = {
                    "target": item["position_in_category"],
                    # "before": before_item["position_in_category"],
                    "before": before_item.get("position_in_category", None) if before_item else None,
                    "change": calculate_diff(item["position_in_category"], before_item["position_in_category"])
                    if before_item
                    else item["position_in_category"],
                }

                item["position_in_shop"] = {
                    "target": item["position_in_shop"],
                    # "before": before_item["position_in_shop"],
                    "before": before_item.get("position_in_shop", None) if before_item else None,
                    "change": calculate_diff(item["position_in_shop"], before_item["position_in_shop"])
                    if before_item
                    else item["position_in_shop"],
                }

                item["available_amount"] = {
                    "target": item["available_amount"],
                    # "before": before_item["available_amount"],
                    "before": before_item.get("available_amount", None) if before_item else None,
                    "change": calculate_diff(item["available_amount"], before_item["available_amount"])
                    if before_item
                    else item["available_amount"],
                }

                item["average_purchase_price"] = {
                    "target": item["average_purchase_price"],
                    # "before": before_item["average_purchase_price"],
                    "before": before_item.get("average_purchase_price", None) if before_item else None,
                    "change": calculate_diff(item["average_purchase_price"], before_item["average_purchase_price"])
                    if before_item
                    else item["average_purchase_price"],
                }

            if len(target_analytics) > 300:
                final_res = [
                    entry
                    for entry in target_analytics
                    if entry["average_purchase_price"]["change"] != 0
                    or (entry["orders"]["change"] != 0 and entry["orders"]["change"] is not None)
                    or (entry["reviews"]["change"] != 0 and entry["reviews"]["change"] is not None)
                    or (entry["rating"]["change"] != 0 and entry["rating"]["change"] is not None)
                    or (entry["available_amount"]["change"] != 0 and entry["available_amount"]["change"] is not None)
                ]
            else:
                final_res = target_analytics

            print("Shop Daily Sales View Time taken: ", time.time() - start)

            return final_res
        except Exception as e:
            print("Error in ShopDailySalesView: ", e)
            traceback.print_exc()
            return None

    def export_to_excel(self, shops_data):
        # Define the path to save the Excel file
        file_path = "shop_daily_report.xlsx"

        # Create a new Excel writer object
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            for shop_name, data in shops_data.items():
                # Convert shop analytics to a pandas DataFrame
                shop_df = pd.DataFrame([data["shop_analytics"]])

                # Convert products analytics to a pandas DataFrame
                products_df = pd.DataFrame(data["products_analytics"])

                # Write shop analytics to the top of the sheet
                shop_df.to_excel(writer, sheet_name=shop_name, startrow=0, index=False)

                # Write products analytics below the shop analytics
                products_df.to_excel(writer, sheet_name=shop_name, startrow=len(shop_df) + 2, index=False)

        return file_path

    def get(self, request, *args, **kwargs):
        try:
            favourite_shops = request.user.favourite_shops.all()

            all_shop_data = {}

            for shop in favourite_shops:
                # Fetch the latest analytics for the shop
                latest_analytics = ShopAnalytics.objects.filter(shop=shop).order_by("-created_at").first()

                # Convert the ShopAnalytics object to a dictionary
                shop_analytics_dict = {
                    "total_products": latest_analytics.total_products,
                    "total_orders": latest_analytics.total_orders,
                    "total_revenue": latest_analytics.total_revenue,
                    "total_reviews": latest_analytics.total_reviews,
                    "average_purchase_price": latest_analytics.average_purchase_price,
                    "average_order_price": latest_analytics.average_order_price,
                    "rating": latest_analytics.rating,
                    "position": latest_analytics.position,
                    "date_pretty": latest_analytics.date_pretty,
                }

                # Fetch the daily product analytics for the shop
                shop_data = self.prepare_shop_statistics(request, shop)

                all_shop_data[shop.title] = {"shop_analytics": shop_analytics_dict, "products_analytics": shop_data}

            # Export the combined shop data to Excel
            file_path = self.export_to_excel(all_shop_data)

            # Create a response with the Excel file
            response = FileResponse(
                open(file_path, "rb"), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = f"attachment; filename={os.path.basename(file_path)}"

            return response

        except Exception as e:
            print("Error in UserDailyReport: ", e)
            return Response(status=500, data={"message": "Internal server error"})

    def send_file_to_telegram_bot(self, chat_id, file_path):
        bot_token = "YOUR_TELEGRAM_BOT_TOKEN"
        send_document_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

        with open(file_path, "rb") as doc_file:
            payload = {
                "chat_id": chat_id,
                "document": doc_file,
                "caption": "Here is your daily report.",  # Optional caption
            }
            response = requests.post(send_document_url, files=payload)
            return response.json()
