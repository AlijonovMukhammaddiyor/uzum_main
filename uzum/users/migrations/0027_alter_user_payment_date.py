# Generated by Django 4.1.9 on 2023-09-11 15:23

from django.db import migrations, models

import uzum.users.models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0026_user_telegram_chat_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="payment_date",
            field=models.DateTimeField(blank=True, default=uzum.users.models.get_week_later, null=True),
        ),
    ]
