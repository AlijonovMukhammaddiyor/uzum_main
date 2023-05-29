import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from uzum.payment.models import Payment


class User(AbstractUser):
    """
    Default custom user model for uzum.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    name = models.CharField(_("Name of User"), blank=True, max_length=255)
    first_name = models.CharField(_("First name"), max_length=30, blank=True)
    last_name = models.CharField(_("Last name"), max_length=150, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    fingerprint = models.CharField(max_length=255, blank=True)  # unique fingerprint of the user's device

    referred_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    # referral_code = models.CharField(unique=True, default=uuid.uuid4().hex[:6].upper(), max_length=6)

    shop = models.ForeignKey("shop.Shop", null=True, blank=True, on_delete=models.SET_NULL)

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
        payments = Payment.objects.filter(user=self).order_by("-payment_date")

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
