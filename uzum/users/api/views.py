import time
import traceback

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.http import HttpRequest
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import UserLoginSerializer, UserSerializer

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
            response = super().create(request, *args, **kwargs)

            if response.status_code == status.HTTP_201_CREATED:
                user = User.objects.get(username=response.data["username"])
                token = UserLoginSerializer.get_token(user)

                # Add refresh and access tokens to the response data
                response.data["access_token"] = str(token.access_token)
                response.data["refresh_token"] = str(token)

            return response

        except IntegrityError as e:
            logger.error("IntegrityError in create: ", e)
            field_errors = str(e.args[1]).split(",")
            error_message = ""

            if "phone_number" in field_errors[0]:
                error_message = "A user with this phone number already exists."
            elif "username" in field_errors[0]:
                error_message = "A user with this username already exists."

            return Response(status=status.HTTP_400_BAD_REQUEST, data={"error": error_message})
        except ValidationError as e:
            logger.error("ValueError in create view: ", e)
            error_message = ""
            error_details = str(e)

            if "phone number" in error_details:
                error_message = "A user with this phone number already exists."
            elif "username" in error_details:
                error_message = "A user with this username already exists."
            else:
                error_message = "An unspecified validation error occurred."

            return Response(status=status.HTTP_400_BAD_REQUEST, data={"error": error_message})
        except Exception as e:
            logger.error("Just Error in create view: ", e)
            traceback.print_exc()
            # send error message
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"error": "Something went wrong"})

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
        data = serializer.data
        # print("before pop: ", data)
        del data["password"]
        del data["is_staff"]
        # print("after pop: ", data)
        return Response(status=status.HTTP_200_OK, data=data)

    @action(detail=False)
    def myTelegramToken(self, request: HttpRequest):
        """
        This method returns the currently authenticated user telegram token.
        Args:
            request (_type_): _description_

        Returns:
            _type_: _description_
        """
        # start = time.time()

        data = {"telegram_token": request.user.telegram_token}
        # print("after pop: ", data)
        return Response(status=status.HTTP_200_OK, data=data)
