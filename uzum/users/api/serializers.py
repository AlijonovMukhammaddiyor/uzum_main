import uuid

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from uzum.referral.models import Referral
from uzum.shop.models import Shop

User = get_user_model()


def get_random_string(length, first_name: str, phone_number: str):
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
            return first_name[:3] + phone_number[3:]

    return random_string


def get_referred_by(referral_code: str):
    try:
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
            "id",
            "username",
            "first_name",
            "last_name",
            "phone_number",
            "fingerprint",
            "referred_by",
            "referral_code",
            "password",
            "email",
            "is_staff",
            # "shop",
        ]

        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "username"},
            # state that referral_code is not required when receiving data
            "referral_code": {"required": False},
            # required fields
            "first_name": {"required": True},
            "last_name": {"required": True},
            "phone_number": {"required": True, "max_length": 20},
            "fingerprint": {"required": True},
            "email": {"required": True, "max_length": 255},
            "password": {"required": True},
            # "shop": {"required": False},
            "referred_by": {"required": False},
            "is_staff": {"required": False},
        }

    def create(self, validated_data: dict):
        # Extract the password from the data
        password = validated_data.pop("password", None)

        if not password:
            raise ValueError("Password is required.")

        # Generate a unique referral code. This will generate a random string of length 6.
        referral_code = get_random_string(6, validated_data["first_name"], validated_data["phone_number"])
        referred_by = get_referred_by(validated_data.get("referral_code"))

        # Add the generated referral code to the user data.
        validated_data["referral_code"] = referral_code
        validated_data["referred_by"] = referred_by
        shop_id = self.context["request"].data.get("shop")
        validated_data["shop"] = get_shop(shop_id)
        validated_data["is_staff"] = validated_data.get("is_staff", False)

        # Create the user instance.
        user = User.objects.create(**validated_data)

        user.set_password(password)
        user.save()

        create_referral(referred_by, user)

        return user


class UserLoginSerializer(TokenObtainPairSerializer):
    """
    Serializer for User Login
    """

    @classmethod
    def get_token(cls, user: User):
        token = super(UserLoginSerializer, cls).get_token(user)

        # Add custom claims
        token["username"] = user.username
        token["first_name"] = user.first_name
        token["last_name"] = user.last_name
        token["phone_number"] = user.phone_number
        token["email"] = user.email
        token["is_developer"] = user.is_developer
        token["referral_code"] = user.referral_code
        token["referred_by"] = user.referred_by
        token["fingerprint"] = user.fingerprint
        token["shop"] = user.shop

        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        refresh = self.get_token(self.user)

        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)

        # Add extra responses here
        data["username"] = self.user.username
        data["email"] = self.user.email
        data["first_name"] = self.user.first_name
        data["last_name"] = self.user.last_name
        data["phone_number"] = self.user.phone_number
        data["is_developer"] = self.user.is_developer
        data["referral_code"] = self.user.referral_code
        data["shop"] = self.user.shop

        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = UserLoginSerializer
