import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, RedirectView, UpdateView
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView
from rest_framework.authentication import TokenAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from config.settings.base import env

User = get_user_model()

client = Client(env("TWILIO_ACCOUNT_SID"), env("TWILIO_AUTH_TOKEN"))
verify = client.verify.services(env("TWILIO_VERIFY_SERVICE_SID"))

# Disable twilio logs
logging.getLogger("twilio").setLevel(logging.INFO)


class VerificationSendView(APIView):
    permission_classes = [AllowAny]
    allowed_methods = ["POST"]

    def post(self, request: Request):
        try:
            data = request.data
            phone_number = data.get("phone_number")
            if not phone_number:
                return Response(status=400, data={"message": "Phone number is required"})
            verify.verifications.create(to=phone_number, channel="sms")

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
                return Response(status=200, data={"message": "Code verified successfully"})

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
    fields = ["first_name", "last_name", "phone_number", "email", "username", "shop"]
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


class CustomObtainAuthToken(ObtainAuthToken):
    """
    Custom ObtainAuthToken view that returns user's credentials with the token.
    """

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        token = Token.objects.get(key=response.data["token"])
        token.user.last_login = timezone.now()
        token.user.save()

        return Response(
            {
                "token": token.key,
                "username": token.user.username,
                "email": token.user.email,
                "phone_number": token.user.phone_number,
                "is_staff": token.user.is_staff,
                "first_name": token.user.first_name,
                "last_name": token.user.last_name,
                "date_joined": token.user.date_joined,
                "referral_code": token.user.referral_code,
            }
        )
