from datetime import timedelta
import datetime
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, RedirectView, UpdateView
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt import authentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.views import TokenObtainPairView
from config.settings.base import env
from uzum.users.api.serializers import (
    CheckUserNameAndPhoneSerializer,
    CookieTokenRefreshSerializer,
    LogOutSerializer,
    PasswordRenewSerializer,
    UserLoginSerializer,
)
from django.utils import timezone

# disable twilio info logs
twilio_logger = logging.getLogger("twilio.http_client")
twilio_logger.setLevel(logging.WARNING)


User = get_user_model()

client = Client(env("TWILIO_ACCOUNT_SID"), env("TWILIO_AUTH_TOKEN"))
verify = client.verify.services(env("TWILIO_VERIFY_SERVICE_SID"))

# Disable twilio logs
logging.getLogger("twilio").setLevel(logging.INFO)


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

            if is_register:
                users = User.objects.filter(phone_number=phone_number)

                if users.exists():
                    return Response(status=400, data={"message": "Phone number already exists"})

            # Calculate the expiration time (e.g., 5 minutes from now)
            expiration_time = timezone.now() + timedelta(minutes=5)

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


class CookieTokenObtainPairView(TokenObtainPairView):
    serializer_class = UserLoginSerializer

    @extend_schema(tags=["token"], operation_id="login")
    def finalize_response(self, request, response, *args, **kwargs):
        if response.status_code == 200:
            response = super().finalize_response(request, response, *args, **kwargs)
            cookie_max_age = 3600 * 24 * 14  # 2 weeks
            response.set_cookie("access_token", response.data["access"], httponly=True)
            response.set_cookie("refresh_token", response.data["refresh"], httponly=True, max_age=cookie_max_age)

            response.data = {"detail": "Cookies Set"}
        return response


class CookieTokenRefreshView(TokenRefreshView):
    @extend_schema(tags=["token"], operation_id="refresh_token")
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        cookie_max_age = 3600 * 24 * 14  # 2 weeks
        response.set_cookie("refresh_token", response.data["refresh"], httponly=True, max_age=cookie_max_age)
        response.set_cookie("access_token", response.data["access"], httponly=True)
        # print("access", response.data["access"])
        return response

    # def finalize_response(self, request, response, *args, **kwargs):
    #     if response.data.get("refresh"):
    #         cookie_max_age = 3600 * 24 * 14  # 14 days
    #         print("New access token generated -> ", response.data["access"])
    #         response.set_cookie("refresh_token", response.data["refresh"], httponly=True, max_age=cookie_max_age)
    #         response.set_cookie("access_token", response.data["access"], httponly=True)
    #         del response.data["refresh"]
    #     return super().finalize_response(request, response, *args, **kwargs)

    # serializer_class = CookieTokenRefreshSerializer


class UserAuthCheckView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [authentication.JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["auth"], operation_id="auth_check")
    def get(self, request, *args, **kwargs):
        return Response({"detail": "Authorized"}, status=200)


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [authentication.JWTAuthentication]
    serializer_class = LogOutSerializer

    @extend_schema(tags=["auth"], operation_id="logout")
    def post(self, request, *args, **kwargs):
        # Logic to invalidate the tokens or clear session-related data
        # For example, you can use Django's built-in logout function:
        from django.contrib.auth import logout

        logout(request)

        # Clear the cookies
        response = Response({"detail": "Logged out"})
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")

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
