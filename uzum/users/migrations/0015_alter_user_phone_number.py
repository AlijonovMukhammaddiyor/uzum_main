# Generated by Django 4.1.9 on 2023-07-23 16:45

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0014_alter_user_phone_number"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="phone_number",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
