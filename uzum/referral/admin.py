from django.contrib import admin

from uzum.referral.models import Referral


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ("referrer", "referred", "referral_date")
    search_fields = (
        "referrer__username",
        "referrer__email",
        "referred__firstname",
        "referred_lastname",
        "referred__email",
    )
    ordering = ("-referral_date",)
