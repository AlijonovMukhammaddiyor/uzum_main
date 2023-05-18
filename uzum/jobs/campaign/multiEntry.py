from uzum.banner.models import Banner
from uzum.jobs.campaign.utils import prepare_banners_data


def create_banners(banners):
    try:
        new_banners = []

        for banner in banners:
            try:
                Banner.objects.get(link=banner["link"])
            except Banner.DoesNotExist:
                new_banners.append(banner)

        banners = prepare_banners_data(new_banners)
        result = Banner.objects.bulk_create(banners, ignore_conflicts=True)

        return result
    except Exception as e:
        print(f"Error in create_banners: {e}")
        return None
