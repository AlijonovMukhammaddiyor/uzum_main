from django.db import models


class Payment(models.Model):
    user = models.ForeignKey("users.User", on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    payment_method = models.CharField(max_length=50)  # e.g., 'Credit Card', 'PayPal'
    payment_id = models.CharField(max_length=50)  # the ID returned by the payment processor

    def __str__(self):
        return f"{self.user} paid {self.amount} on {self.timestamp}"
