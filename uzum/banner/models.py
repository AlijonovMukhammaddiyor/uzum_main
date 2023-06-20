import uuid

from django.db import models


class Banner(models.Model):
    """
    Banner - is the ad banner image on the website to promote either a product or a campaign or shop.
    Args:
        models (_type_): _description_
    """

    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    typename = models.CharField(max_length=1024, default="Banner")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField(null=True, blank=True)
    link = models.TextField(null=True, blank=True)
    image = models.TextField(null=True, blank=True)
    category = models.ForeignKey(
        "category.Category",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
    )
    product = models.ForeignKey("product.Product", on_delete=models.DO_NOTHING, null=True, blank=True)
    campaign = models.ForeignKey("campaign.Campaign", on_delete=models.DO_NOTHING, null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.id} - {self.typename} - {self.created_at} - {self.updated_at} - {self.description} - {self.link} - {self.image} - {self.category} - {self.product} - {self.campaign}"
