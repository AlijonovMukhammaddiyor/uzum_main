# Generated by Django 4.1.9 on 2023-06-21 10:20

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("review", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PopularSeaches",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("words", models.TextField()),
                ("requests_count", models.IntegerField(default=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("date_pretty", models.CharField(blank=True, default="2023-06-21", max_length=1024, null=True)),
            ],
        ),
    ]
