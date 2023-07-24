from django.contrib.auth import get_user_model
import pytz

from config import celery_app
from uzum.users.models import User
from django.utils import timezone


# @celery_app.task()
# def get_users_count():
#     """A pointless Celery task to demonstrate usage."""
#     return User.objects.count()


# @celery_app.task(
#     name="update_user_trials",
# )
# def end_trials():
#     """A pointless Celery task to demonstrate usage."""
#     users = User.objects.filter(is_pro=True)
#     for user in users:
#         if (
#             user.trial_end
#             and user.trial_end < timezone.make_aware(timezone.now(), pytz.timezone("Asia/Tashkent"))
#             and not user.is_paid
#         ):
#             user.is_pro = False
#             user.save()
