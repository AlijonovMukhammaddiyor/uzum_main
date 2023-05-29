import uuid

from django.db import models


class Campaign(models.Model):
    """
    Campaign - is the campaign that is shown on the website to promote a product.
    For example: "Buy 2 get 1 free", "30% off".
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    offer_id = models.IntegerField(default=0)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    typename = models.CharField(max_length=255, null=True, blank=True)

    typename = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.title}"
