from uzum.banner.models import Banner
from uzum.jobs.campaign.utils import (associate_with_shop_or_product,
                                      prepare_banners_data)


def create_banners(banners, product_associations: dict, shop_associations: dict):
    try:
        new_banners = []
        result = {}

        for banner in banners:
            # try:
            #     ban = Banner.objects.get(link=banner["link"])
            #     result[ban.link] = ban
            #     new_banners.append(banner)
            # except Banner.DoesNotExist:
            #     new_banners.append(banner)

            # I decided to create banners everyday repeatedly
            new_banners.append(banner)

        banners_ = prepare_banners_data(new_banners)

        for banner in banners_:
            try:
                ban = Banner.objects.create(**banner)
                result[ban.link] = ban
            except Exception as e:
                print(f"Error in create_banners: {e}")
                continue

        print("Banners created result: ", result)

        for banner in banners:
            assoc = associate_with_shop_or_product(banner["link"])
            if assoc:
                if "product_id" in assoc:
                    print("product_id", assoc["product_id"])
                    if assoc["product_id"] not in product_associations:
                        product_associations[assoc["product_id"]] = []
                    current_banner = result.get(banner["link"], None)
                    if current_banner:
                        product_associations[assoc["product_id"]].append(current_banner)
                elif "shop_id" in assoc:
                    if assoc["shop_id"] not in shop_associations:
                        shop_associations[assoc["shop_id"]] = []

                    current_banner = result.get(banner["link"], None)
                    if current_banner:
                        shop_associations[assoc["shop_id"]].append(current_banner)

        return result
    except Exception as e:
        print(f"Error in create_banners: {e}")
        return None
