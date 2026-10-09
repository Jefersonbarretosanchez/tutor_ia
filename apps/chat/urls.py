from django.urls import path

from apps.chat import views

app_name = "chat"

urlpatterns = [
    path("clara/moment/", views.ClaraMomentView.as_view(), name="clara-moment"),
    path("clara/reply/", views.ClaraReplyView.as_view(), name="clara-reply"),
]
