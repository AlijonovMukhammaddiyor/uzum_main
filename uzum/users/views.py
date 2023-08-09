import datetime
import logging
from datetime import timedelta

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

from config.settings.base import env
from uzum.shop.models import Shop
from uzum.users.api.serializers import (
    CheckUserNameAndPhoneSerializer,
    LogOutSerializer,
    PasswordRenewSerializer,
    UserLoginSerializer,
)

# disable twilio info logs
# twilio_logger = logging.getLogger("twilio.http_client")
# twilio_logger.setLevel(logging.WARNING)


User = get_user_model()

client = Client(env("TWILIO_ACCOUNT_SID"), env("TWILIO_AUTH_TOKEN"))
verify = client.verify.services(env("TWILIO_VERIFY_SERVICE_SID"))

# Disable twilio logs
# logging.getLogger("twilio").setLevel(logging.INFO)


class SetShopsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["POST"]

    def post(self, request: Request):
        try:
            data = request.data
            shop_ids = data.get("shop_ids")
            if not shop_ids:
                return Response(status=400, data={"message": "Shop ids are required"})
            user: User = request.user
            is_pro = user.is_pro

            if not is_pro and not user.is_proplus:
                return Response(status=400, data={"message": "You are not a pro user"})

            if is_pro:
                # only 2 shops is allowed for pro users
                if len(shop_ids) == 0:
                    return Response(status=400, data={"message": "Iltimos, 2 tagacha do'kon tanlang"})

                if len(shop_ids) > 2:
                    return Response(status=400, data={"message": "Iltimos, 2 tagacha do'kon tanlang"})

                shop_id = int(shop_ids[0])
                shop = Shop.objects.get(seller_id=shop_id)
                account_id = shop.account_id

                for shop_id in shop_ids:
                    shop = Shop.objects.get(seller_id=shop_id)
                    if shop.account_id != account_id:
                        return Response(status=400, data={"message": "Do'konlar bir xisobga tegishli bo'lishi kerak"})

                shop_id = int(shop_ids[0])
                shop = Shop.objects.get(seller_id=shop_id)
                user.shops.clear()
                user.shops.add(shop)

                if len(shop_ids) == 2:
                    shop_id = int(shop_ids[1])
                    shop = Shop.objects.get(seller_id=shop_id)
                    user.shops.add(shop)

            elif user.is_proplus:
                #  5 shops is allowed for proplus users
                if len(shop_ids) == 0:
                    return Response(status=400, data={"message": "Iltimos, 5 tagacha do'kon tanlang"})

                if len(shop_ids) > 5:
                    return Response(status=400, data={"message": "Iltimos, 5 tagacha do'kon tanlang"})

                shop_id = int(shop_ids[0])
                shop = Shop.objects.get(seller_id=shop_id)
                account_id = shop.account_id

                for shop_id in shop_ids:
                    shop = Shop.objects.get(seller_id=shop_id)
                    if shop.account_id != account_id:
                        return Response(status=400, data={"message": "Do'konlar bir xisobga tegishli bo'lishi kerak"})

                user.shops.clear()

                for shop_id in shop_ids:
                    shop = Shop.objects.get(seller_id=shop_id)
                    user.shops.add(shop)
            user.save()
            return Response(status=200, data={"message": "Shops successfully set"})
        except Exception as e:
            print("Error in SetShopsView: ", e)
            return Response(status=500, data={"message": "Internal server error"})


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

        response = Response()

        return response


class CustomTokenRefreshView(TokenRefreshView):
    serializer_class = UserLoginSerializer

    @extend_schema(tags=["token"], operation_id="login")
    def post(self, request, *args, **kwargs):
        print("request.data: ", request.data)
        serializer = self.get_serializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        response = Response()

        return response


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
