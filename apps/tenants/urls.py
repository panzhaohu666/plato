"""URL routing for tenants API."""
from django.urls import path
from . import auth_views

urlpatterns = [
    path("register/", auth_views.register, name="auth-register"),
    path("login/", auth_views.login, name="auth-login"),
    path("token/refresh/", auth_views.token_refresh, name="token-refresh"),
]
