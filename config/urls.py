from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views import defaults as default_views
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from uzum.users.views import (
    CheckUserNameAndPhone,
    CodeVerificationView,
    CookieTokenObtainPairView,
    CookieTokenRefreshView,
    LogoutView,
    PasswordRenewView,
    UserAuthCheckView,
    VerificationSendView,
)

urlpatterns = [
    path("", TemplateView.as_view(template_name="pages/home.html"), name="home"),
    path("about/", TemplateView.as_view(template_name="pages/about.html"), name="about"),
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # User management
    path("accounts/", include("allauth.urls")),
    # Your stuff: custom urls includes go here
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# API URLS
urlpatterns += [
    # API base url
    path("api/", include("config.api_router")),
    # DRF auth token
    # path("auth-token/", CustomObtainAuthToken.as_view()),
    path("api/token/", CookieTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/logout/", LogoutView.as_view(), name="token_logout"),
    path("api/token/refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path(
        "api/docs/",
        # add configuration to disbale post and put buttons
        SpectacularSwaggerView.as_view(
            url_name="api-schema",
        ),
        name="api-docs",
    ),
    path("api/users/", include("uzum.users.urls", namespace="users")),
    path("api/category/", include("uzum.category.urls", namespace="category")),
    path("api/shop/", include("uzum.shop.urls", namespace="shop")),
    path("api/product/", include("uzum.product.urls", namespace="product")),
    path("api/badge/", include("uzum.badge.urls", namespace="badge")),
    path("api/banner/", include("uzum.banner.urls", namespace="banner")),
    path("api/username_phone_match", CheckUserNameAndPhone.as_view(), name="check_username"),
    path("api/auth", UserAuthCheckView.as_view(), name="check_username"),
    path("api/newpassword/", view=PasswordRenewView.as_view(), name="check_username"),
    path("api/code/", view=VerificationSendView.as_view(), name="check_username"),
    path("api/verify/", view=CodeVerificationView.as_view(), name="check_username"),
]

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
