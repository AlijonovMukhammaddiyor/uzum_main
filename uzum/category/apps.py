from django.apps import AppConfig

# from uzum.category.tasks import update_uzum_data


class CategoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "uzum.category"

    def ready(self):
        try:
            import uzum.category.tasks  # noqa: F401
        except ImportError:
            pass
