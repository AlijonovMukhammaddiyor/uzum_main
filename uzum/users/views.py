import datetime
import logging
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
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt import authentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from rest_framework_simplejwt.tokens import RefreshToken

from config.settings.base import env
from uzum.shop.models import Shop
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
from uzum.utils.general import Tariffs

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
