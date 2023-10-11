# Generated by Django 4.1.9 on 2023-07-21 06:06

import datetime

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0010_alter_user_is_developer_alter_user_is_pro_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_paid",
            field=models.BooleanField(blank=True, default=False, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="trial_end",
            field=models.DateTimeField(
                blank=True,
                default=datetime.datetime(2023, 7, 22, 6, 6, 56, 483952, tzinfo=datetime.timezone.utc),
                null=True,
            ),
        ),
    ]
