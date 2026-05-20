from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenRefreshView,
    TokenVerifyView,
)

from .views import (
    DevicePermissionViewSet,
    LoginView,
    OrganizationViewSet,
    RegisterView,
    UserViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("organizations", OrganizationViewSet, basename="organization")
router.register("device-permissions", DevicePermissionViewSet, basename="device-permission")

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("register/", RegisterView.as_view(), name="register"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("logout/", TokenBlacklistView.as_view(), name="logout"),
    path("", include(router.urls)),
]
