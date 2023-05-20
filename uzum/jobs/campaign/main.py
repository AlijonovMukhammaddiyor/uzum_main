from collections import defaultdict

from uzum.jobs.campaign.multiEntry import create_banners
from uzum.jobs.campaign.singleEntry import create_campaign
from uzum.jobs.campaign.utils import get_campaign_products_ids, get_main_page_data, prepare_banners_data


def update_or_create_campaigns():
    """
    This function will create or update campaigns.
    """
    try:
        main_content = get_main_page_data()
        product_associations = {}
        shop_associations = {}
        product_campaigns = defaultdict(list)

        if main_content:
            for content in main_content:
                print(f"Content - {content['__typename']}")
                if content["__typename"] == "BannerBlock":
                    # it is banners
                    banners = content["content"]
                    create_banners(banners, product_associations, shop_associations)
                    # banners.extend(prepare_banners_data(banners_api))
                if content["__typename"] == "InlineBanner":
                    create_banners([content], product_associations, shop_associations)
                    # banners.append(prepare_banners_data([content]))

                if content["__typename"] == "ExtendableOffer" or content["__typename"] == "CarouselOffer":
                    product_ids: list = get_campaign_products_ids(content["category"]["id"], content["title"])
                    print(f"product_ids for {content['title']}: {len(product_ids)}")
                    campaign = create_campaign(content)
                    for product in product_ids:
                        product_campaigns[product].append(campaign)

        return product_campaigns, product_associations, shop_associations
    except Exception as e:
        print(f"Error in update_or_create_campaigns: {e}")
        return None
