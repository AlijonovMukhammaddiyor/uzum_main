from uzum.sku.models import Sku


def find_sku(sku: int):
    try:
        result = Sku.objects.get(sku=sku)
        return result

    except Exception as _:
        return None
