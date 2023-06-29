from rest_framework import permissions
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJSONWebTokenAuthentication(JWTAuthentication):
    def get_raw_token(self, request):
        print("getting raw token")
        return request.COOKIES.get("access_token")


class IsAdminOrDeveloper(permissions.BasePermission):
    def has_permission(self, request, view):
        try:
            print(request.user.is_superuser, request.user.is_developer)
            # Check if the user is a developer.
            if request.user.is_developer:
                return True

            if request.user.is_superuser:
                return True

            # If neither of the above, deny permission.
            return False
        except AttributeError as e:
            print("AttributeError in IsAdminOrDeveloper: ", e)
            return False
