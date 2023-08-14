from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from uzum.users.forms import UserAdminChangeForm, UserAdminCreationForm
from uzum.users.models import User


@admin.register(User)
class CustomUserAdmin(auth_admin.UserAdmin):
    add_form = UserAdminCreationForm
    form = UserAdminChangeForm
    model = User
    list_display = ("username", "phone_number", "email", "is_staff", "is_developer", "tariff")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "phone_number", "email")}),
        ("Additional Info", {"fields": ("fingerprint", "referred_by", "referral_code", "is_developer")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
