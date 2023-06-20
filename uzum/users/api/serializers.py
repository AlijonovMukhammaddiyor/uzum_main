import uuid

from django.contrib.auth import get_user_model
from phone_verify.serializers import SMSVerificationSerializer

from rest_framework import serializers
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
