import uuid
from django.db import models


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
    amount = models.FloatField(null=True, blank=True)
    order_id = models.BigIntegerField(null=True, blank=True, unique=True)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE)

    def __str__(self):
        return f"User: {self.user} - Order: {self.order_id} - Amount: {self.amount}"
