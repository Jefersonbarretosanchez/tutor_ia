from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("password/", views.password_change, name="password_change"),
    path("", views.dashboard, name="dashboard"),
    # Matrículas
    path("enrollments/", views.enrollment_list, name="enrollment_list"),
    path("enrollments/<int:pk>/reactivate/", views.enrollment_reactivate, name="enrollment_reactivate"),
    path("enrollments/<int:pk>/credit/", views.enrollment_credit, name="enrollment_credit"),
    # Conversaciones
    path("conversations/", views.conversation_list, name="conversation_list"),
    path("conversations/<int:pk>/", views.conversation_detail, name="conversation_detail"),
    # Usuarios y roles
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_form, name="user_create"),
    path("users/<int:pk>/", views.user_form, name="user_edit"),
    path("users/<int:pk>/delete/", views.user_delete, name="user_delete"),
    path("roles/", views.role_list, name="role_list"),
    path("roles/new/", views.role_create, name="role_create"),
    path("roles/<int:pk>/", views.role_matrix, name="role_matrix"),
    path("roles/<int:pk>/delete/", views.role_delete, name="role_delete"),
    # Gates: acción especial
    path("gates/<int:pk>/lock/", views.gate_lock, name="gate_lock"),
    # Recursos genéricos (courses, gates, default_gates, flows, prompts, students, ledger, launch_logs, audit)
    path("r/<str:key>/", views.resource_list, name="resource_list"),
    path("r/<str:key>/new/", views.resource_form, name="resource_create"),
    path("r/<str:key>/<int:pk>/", views.resource_form, name="resource_edit"),
    path("r/<str:key>/<int:pk>/delete/", views.resource_delete, name="resource_delete"),
]
