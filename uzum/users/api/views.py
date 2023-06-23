from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.http import HttpResponseBadRequest
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from config.settings.base import env
from .serializers import UserSerializer

User = get_user_model()


class UserViewSet(CreateModelMixin, RetrieveModelMixin, ListModelMixin, UpdateModelMixin, GenericViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()
    lookup_field = "username"

    def get_permissions(self):
        """
        Override this method to set custom permissions for different actions
        """
        if self.action == "create":
            # Allow any user (authenticated or not) to create a new user
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self, *args, **kwargs):
        assert isinstance(self.request.user.id, int)  # for mypy to know that the user is authenticated
        return self.queryset.filter(id=self.request.user.id)

    def create(self, request, *args, **kwargs):
        # Check if the verification token cookie is present
        # ! uncomment below after deploying
        # if "verification_token" not in request.COOKIES:
        #     return HttpResponseBadRequest("Missing verification token")

        # # Retrieve the verification token from the cookie
        # verification_token = request.COOKIES["verification_token"]

        # # Verify the token against your validation logic
        # if not env("VERIFICATION_TOKEN") == verification_token:
        #     return HttpResponseBadRequest("Invalid verification token")

        # Continue with the user creation logic
        return super().create(request, *args, **kwargs)

    @action(detail=False)
    def me(self, request: HttpRequest):
        """
        This method returns the currently authenticated user.
        Args:
            request (_type_): _description_

        Returns:
            _type_: _description_
        """
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)
