from datetime import timedelta
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config.settings.base import env
from uzum.payment.models import MerchatTransactionsModel
from uzum.utils.general import Tariffs


def get_current_time():
    return timezone.now() + timedelta(days=1)


def get_one_day_later():
    return timezone.now() + timedelta(days=1)


def get_week_later():
    return timezone.now() + timedelta(days=7)


class User(AbstractUser):
    """
    Default custom user model for uzum.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    AUTHENTICATION_METHODS = [
        ("STANDARD", "Standard Registration"),
        ("GOOGLE", "Google OAuth"),
        ("TELEGRAM", "Telegram"),
        ("PHONE", "Phone"),
    ]

    # make choices for tariffs

    phone_number = models.CharField(max_length=20, blank=True, unique=False, null=True)
    # is_verified = models.BooleanField(default=False)
    email = models.EmailField(_("Email address"), blank=True, unique=False)
    fingerprint = models.CharField(max_length=255, blank=True)  # unique fingerprint of the user's device

    referred_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    referral_code = models.CharField(unique=True, max_length=6)

    shops = models.ManyToManyField("shop.Shop", blank=True)

    is_developer = models.BooleanField(default=False, null=True, blank=True)
    # is_proplus = models.BooleanField(default=False, null=True, blank=True)
    # is_pro = models.BooleanField(default=True, null=True, blank=True)
    # is_enterprise = models.BooleanField(default=False, null=True, blank=True)

    # trial_end = models.DateTimeField(default=get_current_time, null=True, blank=True)
    # is_paid = models.BooleanField(default=False, null=True, blank=True)
    tariff = models.CharField(  # tariff name
        max_length=10,
        choices=Tariffs.choices,
        default=Tariffs.TRIAL,
    )
    payment_date = models.DateTimeField(
        null=True,
        blank=True,
        default=get_week_later,
    )
    shops_updated_at = models.DateTimeField(null=True, blank=True)
    authentication_method = models.CharField(
        max_length=10,
        choices=AUTHENTICATION_METHODS,
        default=AUTHENTICATION_METHODS[0][0],
    )
    favourite_shops = models.ManyToManyField("shop.Shop", blank=True, related_name="favourite_shops")
    favourite_products = models.ManyToManyField("product.Product", blank=True, related_name="favourite_products")
    telegram_token = models.UUIDField(default=uuid.uuid4, null=True, unique=True)
    is_telegram_connected = models.BooleanField(default=False)
    telegram_chat_id = models.CharField(max_length=255, null=True, blank=True)

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.
        """
        return reverse("users:detail", kwargs={"username": self.username})

    def get_next_payment_date(self):
        """Get the date of the user's next payment.
        We give users 1 day free trial, so if they have no payments yet,
        the next payment date will be 1 day after their registration date.
        Returns:
            datetime.date: The date of the user's next payment.
        """
        payments = MerchatTransactionsModel.objects.filter(user=self).order_by("-payment_date")

        if len(payments) == 0:
            return self.date_joined + timedelta(days=1)

        last_payment = payments.first()

        if last_payment:
            # The user has at least one payment, calculate next date based on last payment date
            next_payment_date = last_payment.timestamp + timedelta(days=30)
        else:
            # The user has no payments yet, calculate next date based on registration date
            next_payment_date = self.date_joined + timedelta(days=1)
        return next_payment_date


@receiver(post_save, sender=User)
def start_trial(sender, instance: User, created, **kwargs):
    if created:
        webhook_url = "https://hooks.slack.com/services/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"
        referral_webhook_url = "https://hooks.slack.com/services/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"
        referrals_umarbek = "https://hooks.slack.com/services/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"
        referral_soff = "https://hooks.slack.com/services/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"

        block = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Username - {instance.username}\n Referred by - {instance.referred_by.username if instance.referred_by else 'No One'}\n Tariff - {instance.tariff}\n",
                },
            }
        ]

        try:
            requests.post(webhook_url, json={"text": "New user signed up\n", "blocks": block})
            if instance.referred_by and instance.referred_by.referral_code == "invest":
                requests.post(
                    referral_webhook_url,
                    json={
                        "text": "New user signed up",
                        "blocks": block,
                    },
                )

            if instance.referred_by and instance.referred_by.referral_code == "681332":
                requests.post(
                    referrals_umarbek,
                    json={
                        "text": "New user signed up",
                        "blocks": block,
                    },
                )

            if instance.referred_by and instance.referred_by.referral_code == "0746b5":
                requests.post(
                    referral_soff,
                    json={
                        "text": "New user signed up",
                        "blocks": block,
                    },
                )

        except SlackApiError as e:
            print(f"Error: {e}")
