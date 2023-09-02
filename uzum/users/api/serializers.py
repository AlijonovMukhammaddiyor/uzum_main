from datetime import datetime, timedelta
import traceback
import uuid

from django.contrib.auth import get_user_model
import pytz
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from uzum.referral.models import Referral
from uzum.shop.models import Shop

User = get_user_model()
import logging

logger = logging.getLogger(__name__)


def get_random_string(length, username: str, phone_number: str):
    """
    Generate a random string of length characters.
    """
    random_string = str(uuid.uuid4()).replace("-", "")[:length]

    i = 0
    while User.objects.filter(referral_code=random_string).exists():
        random_string = str(uuid.uuid4()).replace("-", "")[:length]
        i += 1

        if i > 10:
            print("Could not generate a unique referral code after 10 attempts.")
            # return phone number and 3 letters of name
            return username[:3] + phone_number[3:]

    return random_string


def get_referred_by(referral_code: str):
    try:
        print("code: ", referral_code)

        if referral_code:
            return User.objects.get(referral_code=referral_code)
        return None
    except User.DoesNotExist:
        return None


def get_shop(shop_id: int):
    try:
        if shop_id:
            return Shop.objects.get(seller_id=shop_id)
        return None
    except Shop.DoesNotExist:
        return None


def create_referral(referrer: User, referred: User):
    try:
        if not referrer or not referred:
            return None
        referral = Referral.objects.create(referrer=referrer, referred=referred)
        return referral
    except Exception as e:
        print(e)
        return None


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "username",
            "phone_number",
            "referral_code",
            "password",
            "email",
            "is_staff",
            "tariff",
            "shops_updated_at",
        ]

        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "username"},
            "referral_code": {"required": False},
            "username": {"required": True, "max_length": 255},
            "phone_number": {"required": False, "max_length": 20},
            "fingerprint": {"required": False},
            "email": {"required": False, "max_length": 255},
            "password": {"required": False},
            "referred_by": {"required": False},
            "is_staff": {"required": False},
            "shops_updated_at": {"required": False},
            "tariff": {"required": False},
        }

    def create(self, validated_data: dict):
        try:
            # Extract the password from the data
            password = validated_data.pop("password", None)
            print("validated_data: ", validated_data)
            if not password:
                raise ValueError("Password is required.")

            phone_number = validated_data.get("phone_number")
            if phone_number:
                if User.objects.filter(phone_number=phone_number).exists():
                    raise ValueError("A user with this phone number already exists.")

            if validated_data.get("username"):
                if User.objects.filter(username=validated_data["username"]).exists():
                    raise ValueError("A user with this username already exists.")

            # Generate a unique referral code. This will generate a random string of length 6.
            referral_code = get_random_string(6, validated_data["username"], validated_data["username"])
            # replace space with underscore
            validated_data["username"] = validated_data["username"].replace(" ", "_")
            context = self.context["request"].data
            referred_by_code = context.get("referred_by_code")
            referred_by = get_referred_by(referred_by_code)
            # Add the generated referral code to the user data.
            validated_data["referral_code"] = referral_code
            validated_data["referred_by"] = referred_by
            validated_data["is_staff"] = validated_data.get("is_staff", False)
            validated_data["fingerprint"] = validated_data.get("fingerprint", "")

            if referred_by_code and referred_by_code == "invest":
                # set to 1 week
                validated_data["payment_date"] = (datetime.now() + timedelta(days=7)).astimezone(
                    pytz.timezone("Asia/Tashkent")
                )

            logger.warning("Creating new user with data: ", validated_data)

            # Create the user instance.
            user = User(**validated_data)
            user.set_password(password)
            user.save()

            create_referral(referred_by, user)
            # before returning the user, we need to remove the password from the validated data
            return user
        except ValueError as e:
            logger.error("ValueError in create: ", e)
            raise e
        except Exception as e:
            print("Error in create: ", e)
            logger.error(traceback.format_exc())
            traceback.print_exc()
            return e


class UserLoginSerializer(TokenObtainPairSerializer):
    """
    Serializer for User Login
    """

    @classmethod
    def get_token(cls, user: User):
        token = super(UserLoginSerializer, cls).get_token(user)

        # Add custom claims
        token["user"] = {
            "username": user.username,
            "referral_code": user.referral_code,
            "tariff": user.tariff,
            "referred_by": user.referred_by.referral_code if user.referred_by else None,
        }

        print("token: ", token)

        return token


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        # Let the default TokenRefreshSerializer handle the validation
        data = super().validate(attrs)

        # Decode the new access token without verification to get its payload
        decoded_payload = AccessToken(data["access"]).payload

        # Assuming you have user_id in your payload (default behavior of simple jwt)
        user = User.objects.get(id=decoded_payload["user_id"])

        # Add custom claims to the payload
        decoded_payload["username"] = user.username
        decoded_payload["referral_code"] = getattr(user, "referral_code", None)
        decoded_payload["tariff"] = getattr(user, "tariff", "free")
        decoded_payload["referred_by"] = user.referred_by.referral_code if user.referred_by else None

        print("decoded_payload: ", decoded_payload)
        # Create a new access token with the modified payload
        access_token = AccessToken()
        access_token.payload = decoded_payload

        # Update the access token in the data
        data["access"] = str(access_token)

        refresh_payload = RefreshToken(data["refresh"]).payload
        refresh_payload["username"] = user.username
        refresh_payload["referral_code"] = getattr(user, "referral_code", None)
        refresh_payload["tariff"] = getattr(user, "tariff", "free")
        refresh_payload["referred_by"] = user.referred_by.referral_code if user.referred_by else None
        refresh_token = RefreshToken()
        refresh_token.payload = refresh_payload
        refresh_token.payload["user"] = {
            "username": user.username,
            "referral_code": user.referral_code,
            "tariff": user.tariff,
        }
        data["refresh"] = str(refresh_token)

        return data


class CheckUserNameAndPhoneSerializer(serializers.Serializer):
    """
    Serializer for checking username and phone number
    """

    username = serializers.CharField(max_length=255)
    phone_number = serializers.CharField(max_length=20)


class PasswordRenewSerializer(serializers.Serializer):
    """
    Serializer for password renew
    """

    username = serializers.CharField(max_length=255)
    phone_number = serializers.CharField(max_length=20)
    password = serializers.CharField(max_length=255)


class LogOutSerializer(serializers.Serializer):
    """
    Serializer for logging out
    """

    pass
