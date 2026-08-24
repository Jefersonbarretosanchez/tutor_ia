from django.urls import path

from apps.lti_tool import views

app_name = "lti_tool"

urlpatterns = [
    path("login/", views.login, name="login"),
    path("launch/", views.launch, name="launch"),
    path("jwks/", views.jwks, name="jwks"),
]
