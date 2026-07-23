from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register_user),
    path("login/", views.login_user),
    path("me/", views.me),
    path("logout/", views.logout_user),
]