from rest_framework import permissions


class IsAdminOrDeveloper(permissions.BasePermission):
    def has_permission(self, request, view):
        print(request.user.is_superuser, request.user.is_developer)
        # Check if the user is an admin.
        if request.user.is_superuser:
            return True

        # Check if the user is a developer.
        if request.user.is_developer:
            return True

        # If neither of the above, deny permission.
        return False
