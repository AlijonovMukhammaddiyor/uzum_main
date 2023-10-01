from django.db import models


# Create your models here.
class Brand(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    image = models.TextField(null=True, blank=True)
