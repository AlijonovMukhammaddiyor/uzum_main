from django.contrib import admin

from uzum.payment.models import MerchatTransactionsModel


@admin.register(MerchatTransactionsModel)
class MerchatTransactionsModelAdmin(admin.ModelAdmin):
    # list_display = ("user", "timestamp", "amount", "payment_method", "payment_id")
    # search_fields = ("user__username", "user__email")
    # list_filter = ("payment_method",)
    # ordering = ("-timestamp",)
    pass
