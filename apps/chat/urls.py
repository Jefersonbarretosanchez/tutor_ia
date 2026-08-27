from django.urls import path

from apps.chat import views

app_name = "chat"

urlpatterns = [
    path("templates/", views.TemplateListView.as_view(), name="template-list"),
    path("sessions/", views.SessionStartView.as_view(), name="session-start"),
    path("sessions/<int:session_id>/messages/", views.MessageCreateView.as_view(), name="message-create"),
    path("clara/moment/", views.ClaraMomentView.as_view(), name="clara-moment"),
    path("clara/reply/", views.ClaraReplyView.as_view(), name="clara-reply"),
]
