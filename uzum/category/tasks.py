from datetime import datetime

import pytz
from celery.schedules import crontab

from config import celery_app
from uzum.jobs.category.main import create_and_update_categories
from uzum.jobs.product.main import create_and_update_products
from uzum.product.models import get_today_pretty


@celery_app.task(
    name="update_uzum_data",
)
def update_uzum_data(args=None, **kwargs):
    print(get_today_pretty())
    print(datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%H:%M:%S" + " - " + "%d/%m/%Y"))
    create_and_update_categories()
    create_and_update_products()
    print("Uzum data updated...")
