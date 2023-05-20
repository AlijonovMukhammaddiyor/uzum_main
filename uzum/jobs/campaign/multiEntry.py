from uzum.banner.models import Banner
from uzum.jobs.campaign.utils import associate_with_shop_or_product, prepare_banners_data


def create_banners(banners, product_associations: dict, shop_associations: dict):
    try:
        new_banners = []

        for banner in banners:
            try:
                Banner.objects.get(link=banner["link"])
            except Banner.DoesNotExist:
                new_banners.append(banner)

        banners_ = prepare_banners_data(new_banners)
        result = Banner.objects.bulk_create(banners_, ignore_conflicts=True)

        for banner in banners:
            assoc = associate_with_shop_or_product(banner['link'])
            if assoc:
                if "product_id" in assoc:
                    if assoc["product_id"] not in product_associations:
                        product_associations[assoc["product_id"]] = []
                    current_banner = None
                    for b in result:
                        if b.link == banner["link"]:
                            current_banner = b
                            break
                    if current_banner:
                        product_associations[assoc["product_id"]].append(current_banner)
                elif "shop_id" in assoc:
                    if assoc["shop_id"] not in shop_associations:
                        shop_associations[assoc["shop_id"]] = []

                    current_banner = None
                    for b in result:
                        if b.link == banner["link"]:
                            current_banner = b
                            break
                    if current_banner:
                        shop_associations[assoc["shop_id"]].append(current_banner)

        return result
    except Exception as e:
        print(f"Error in create_banners: {e}")
        return None
