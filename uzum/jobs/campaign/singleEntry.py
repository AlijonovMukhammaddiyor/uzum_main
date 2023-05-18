from uzum.campaign.models import Campaign

# offer_id = models.IntegerField(default=0)
#     title = models.CharField(max_length=255)
#     description = models.TextField(null=True, blank=True)
#     typename = models.CharField(max_length=255, null=True, blank=True)

#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)


def create_campaign(campaign_api):
    try:
        try:
            campaign = Campaign.objects.get(title=campaign_api["title"])
        except Campaign.DoesNotExist:
            campaign = Campaign.objects.create(
                title=campaign_api["title"],
                description=campaign_api["description"],
                typename=campaign_api["__typename"],
                offer_id=campaign_api["category"]["id"],
            )
        return campaign
    except Exception as e:
        print(f"Error in create_campaign: {e}")
        return None
