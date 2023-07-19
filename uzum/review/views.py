# from django.shortcuts import render

# Create your views here.
from django.http import HttpRequest
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication


def enforce_csrf(request, get_response):
    """
    Enforce CSRF validation.
    """
    check = CSRFCheck(get_response=get_response)
    # populates request.META['CSRF_COOKIE'], which is used in process_view()
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        # CSRF failed, bail with explicit error message
        raise exceptions.PermissionDenied("CSRF Failed: %s" % reason)


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request: HttpRequest):
        # print("request", request, request.COOKIES)
        header = self.get_header(request)
        if header is None:
            raw_token = request.COOKIES.get("access") or None
        else:
            raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        # print("Header", header, raw_token)

        validated_token = self.get_validated_token(raw_token)
        enforce_csrf(request, lambda: None)
        return self.get_user(validated_token), validated_token
