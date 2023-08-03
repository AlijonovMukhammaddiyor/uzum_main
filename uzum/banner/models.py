import uuid

from django.db import models

from uzum.product.models import Product


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
        return f"{self.id} - {self.created_at} - {self.link}"

    @staticmethod
    def set_products():
        try:
            for banner in Banner.objects.filter(product=None):
                # Check if banner link includes '/product'
                if "/product" in banner.link:
                    # Split the URL by '?'
                    url_before_parameters = banner.link.split("?", 1)[0]
                    # Generate the product id
                    product_id_str = url_before_parameters.rsplit("-", 1)[-1]  # take the string after the last '-'
                    try:
                        product_id = int(product_id_str)  # convert the string to UUID
                        # Find the product
                        product = Product.objects.get(product_id=product_id)
                        # Set it to the product foreign key
                        banner.product = product
                        banner.save()
                    except (
                        ValueError,
                        Product.DoesNotExist,
                    ):  # catch exceptions if the product_id is not a valid UUID or the product does not exist
                        print(f"Invalid product id: {product_id_str} in banner link: {banner.link}")
                        continue
        except Exception as e:
            print("Error in set_products: ", e)
