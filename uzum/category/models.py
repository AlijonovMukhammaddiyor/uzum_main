import uuid

from django.db import models


class Category(models.Model):
    categoryId = models.IntegerField(unique=True, null=False, blank=False, primary_key=True)

    title = models.CharField(max_length=1024)
    seo = models.TextField(blank=True, null=True)

    adult = models.BooleanField(default=False, db_index=True)

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        blank=True,
        related_name="child_categories",
        null=True,
    )
    children = models.ManyToManyField("self", blank=True, symmetrical=False, related_name="parent_cats")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    def __str__(self):
        return self.title + " " + str(self.categoryId)


class CategoryAnalytics(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    category = models.ForeignKey(
        Category,
        on_delete=models.DO_NOTHING,
    )

    totalProducts = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.category.categoryId}: {self.totalProducts}"
