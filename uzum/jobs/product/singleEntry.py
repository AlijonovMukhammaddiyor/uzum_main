from datetime import datetime

import pytz

from uzum.product.models import Product, ProductAnalytics


def does_product_exist(product_id):
    return Product.objects.filter(product_id=product_id).exists()


def find_product(product_id):
    try:
        return Product.objects.get(product_id=product_id)
    except Product.DoesNotExist:
        return None


def create_product(product_id, shop):
    try:
        product = Product.objects.create(product_id=product_id, shop=shop)
        shop.products.add(product)

        return product
    except Exception as e:
        print(f"Error in createProduct: {e}")
        return None


def update_product(product_id, newData):
    try:
        product = Product.objects.get(product_id=product_id)
        for key in newData:
            setattr(product, key, newData[key])
        product.save()

        return product
    except Exception as e:
        print(f"Error in updateProduct: {e}")
        return None


def create_product_analytics(product_id, totalReviews, rating, totalOrders):
    try:
        product = Product.objects.get(product_id=product_id)
        productAnalytics = ProductAnalytics.objects.create(
            product=product,
            reviews_amount=totalReviews,
            rating=rating,
            orders_amount=totalOrders,
            created_at=datetime.now(tz=pytz.timezone("Asia/Tashkent")),
        )

        return productAnalytics
    except Exception as e:
        print(f"Error in createProductAnalytics: {e}")
        return None
