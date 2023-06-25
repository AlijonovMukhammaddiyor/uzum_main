from django.db import models

from uzum.users.models import User


class Referral(models.Model):
    referrer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="referrals_made")
    referred = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="referrals_received", null=True)
    referral_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("referrer", "referred")  # Ensure that a referrer/referred pair is unique
