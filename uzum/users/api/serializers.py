import traceback
import uuid

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from uzum.referral.models import Referral
from uzum.shop.models import Shop

User = get_user_model()


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
        users = User.objects.all()
        for user in users:
            print("user: ", user.referral_code)

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
            # Create the user instance.
            user = User.objects.create(**validated_data)
            user.set_password(password)
            user.save()

            create_referral(referred_by, user)
            # before returning the user, we need to remove the password from the validated data
            return {
                "id": user.id,
                "username": user.username,
                "referral_code": user.referral_code,
            }
        except Exception as e:
            print("Error in create: ", e)
            traceback.print_exc()
            return None


class UserLoginSerializer(TokenObtainPairSerializer):
    """
    Serializer for User Login
    """

    @classmethod
    def get_token(cls, user: User):
        token = super(UserLoginSerializer, cls).get_token(user)

        # Add custom claims
        # token["user"] = {
        #     "username": user.username,
        #     "phone_number": user.phone_number,
        #     "email": user.email,
        #     "is_staff": user.is_staff,
        #     "referral_code": user.referral_code,
        #     "shop": user.shop,
        # }

        return token


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    refresh = None  # Remove the default refresh field

    def validate(self, attrs):
        refresh = self.context["request"].COOKIES.get("refresh")  # Get the refresh token from cookies

        if refresh is None:
            raise InvalidToken("No valid token found in cookie")

        attrs["refresh"] = refresh
        return super().validate(attrs)


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
