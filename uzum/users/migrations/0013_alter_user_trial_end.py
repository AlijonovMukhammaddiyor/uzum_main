# Generated by Django 4.1.9 on 2023-07-23 01:46

from django.db import migrations, models

import uzum.users.models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0012_alter_user_is_pro_alter_user_trial_end"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="trial_end",
            field=models.DateTimeField(blank=True, default=uzum.users.models.get_current_time, null=True),
        ),
    ]
