from django.db import models


class Badge(models.Model):
    """
    Badge - is the badge that is shown on the product card.
    For example: "Sale", "30% off".
    """
    badge_id = models.IntegerField(unique=True, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    text = models.TextField(null=True, blank=True)
    type = models.CharField(max_length=255, null=True, blank=True)
    link = models.TextField(null=True, blank=True)
    textColor = models.CharField(max_length=255, null=True, blank=True)
    backgroundColor = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.badge_id} - {self.text}"
