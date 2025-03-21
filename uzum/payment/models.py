import uuid

from django.db import models

from uzum.utils.general import Tariffs

PRO = 39 * 12137.70 * 100
PREMIUM = 59 * 12137.70 * 100
ENTERPRISE = 99 * 12137.70 * 100


class MerchatTransactionsModel(models.Model):
    """
    MerchatTransactionsModel class \
        That's used for managing transactions in database.
    """

    _id = models.CharField(max_length=255, null=True, blank=False)
    transaction_id = models.CharField(max_length=255, null=True, blank=False, default=uuid.uuid4)
    # order_id = models.BigIntegerField(null=True, blank=True, unique=True)
    amount = models.FloatField(null=True, blank=True)
    time = models.BigIntegerField(null=True, blank=True)
    perform_time = models.BigIntegerField(null=True, default=0)
    cancel_time = models.BigIntegerField(null=True, default=0)
    state = models.IntegerField(null=True, default=1)
    reason = models.CharField(max_length=255, null=True, blank=True)
    created_at_ms = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE)
    order = models.ForeignKey("Order", on_delete=models.CASCADE)

    def __str__(self):
        return str(self._id)


class Order(models.Model):
    # define order status choices
    ORDER_STATUS = (
        (1, "Requested"),
        (2, "Created"),
        (3, "Performed"),
        (4, "Canceled"),
    )

    amount = models.FloatField(null=True, blank=True)
    order_id = models.AutoField(primary_key=True)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE)
    months = models.IntegerField(default=1)
    status = models.IntegerField(choices=ORDER_STATUS, default=1)
    tariff = models.CharField(
        max_length=10,
        choices=Tariffs.choices,
        default=Tariffs.BASE,
    )

    def __str__(self):
        return f"User: {self.user} - Order: {self.order_id} - Amount: {self.amount}"
