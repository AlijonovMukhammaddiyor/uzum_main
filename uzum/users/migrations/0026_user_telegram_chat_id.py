# Generated by Django 4.1.9 on 2023-09-05 22:48

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0025_alter_user_telegram_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="telegram_chat_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
