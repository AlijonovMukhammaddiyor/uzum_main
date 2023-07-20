import time
import traceback

from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponseBadRequest
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db import IntegrityError
from rest_framework.exceptions import ValidationError
from config.settings.base import env

from .serializers import UserSerializer

User = get_user_model()
import logging

logger = logging.getLogger(__name__)


class UserViewSet(CreateModelMixin, RetrieveModelMixin, ListModelMixin, UpdateModelMixin, GenericViewSet):
    serializer_class = UserSerializer
    authentication_classes = [JWTAuthentication]
    queryset = User.objects.all()
    lookup_field = "username"

    def get_permissions(self):
        """
        Override this method to set custom permissions for different actions
        """
        if self.action == "create" or self.action == "check_username_phone_match":
            # Allow any user (authenticated or not) to create a new user
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self, *args, **kwargs):
        try:
            assert isinstance(self.request.user.id, int)  # for mypy to know that the user is authenticated
            return self.queryset.filter(id=self.request.user.id)
        except AssertionError:
            return self.queryset.none()

    def create(self, request, *args, **kwargs):
        try:
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
        except IntegrityError as e:
            field_errors = str(e.args[1]).split(",")
            error_message = ""

            if "phone_number" in field_errors[0]:
                error_message = "A user with this phone number already exists."
            elif "username" in field_errors[0]:
                error_message = "A user with this username already exists."

            return Response(status=status.HTTP_400_BAD_REQUEST, data={"error": error_message})
        except ValidationError as e:
            error_message = ""
            error_details = e.detail  # This should be a dictionary with the error details.

            if "phone_number" in error_details:
                error_message = "A user with this phone number already exists."
            elif "username" in error_details:
                error_message = "A user with this username already exists."

            return Response(status=status.HTTP_400_BAD_REQUEST, data={"error": error_message})
        except Exception as e:
            print("Error in create: ", e)
            traceback.print_exc()
            # send error message
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"error": str(e)})

    @action(detail=False)
    def me(self, request: HttpRequest):
        """
        This method returns the currently authenticated user.
        Args:
            request (_type_): _description_

        Returns:
            _type_: _description_
        """
        # start = time.time()
        serializer = UserSerializer(request.user, context={"request": request})
        # print(f"Time taken by current user: {time.time() - start}")
        # logging.info(f"Time taken by current user: {serializer.data}")
        return Response(status=status.HTTP_200_OK, data=serializer.data)
