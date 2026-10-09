from django.urls import path, register_converter

from . import views
from .converters import ResourceConverter

register_converter(ResourceConverter, "resource")

app_name = "portal"

urlpatterns = [
    path("ingresar/", views.login_view, name="login"),
    path("salir/", views.logout_view, name="logout"),
    path("contrasena/", views.password_change, name="password_change"),
    path("", views.dashboard, name="dashboard"),
    path("buscar/", views.search, name="search"),
    # Matrículas
    path("matriculas/", views.enrollment_list, name="enrollment_list"),
    path("matriculas/<int:pk>/reactivar/", views.enrollment_reactivate, name="enrollment_reactivate"),
    path("matriculas/<int:pk>/reiniciar/", views.enrollment_reset_chat, name="enrollment_reset_chat"),
    path("matriculas/<int:pk>/acreditar/", views.enrollment_credit, name="enrollment_credit"),
    # Conversaciones
    path("conversaciones/", views.conversation_list, name="conversation_list"),
    path("conversaciones/<int:pk>/", views.conversation_detail, name="conversation_detail"),
    path("conversaciones/<int:pk>/reiniciar/", views.conversation_reset, name="conversation_reset"),
    # Usuarios y roles
    path("usuarios/", views.user_list, name="user_list"),
    path("usuarios/nuevo/", views.user_form, name="user_create"),
    path("usuarios/<int:pk>/", views.user_form, name="user_edit"),
    path("usuarios/<int:pk>/eliminar/", views.user_delete, name="user_delete"),
    path("roles/", views.role_list, name="role_list"),
    path("roles/nuevo/", views.role_create, name="role_create"),
    path("roles/<int:pk>/", views.role_matrix, name="role_matrix"),
    path("roles/<int:pk>/eliminar/", views.role_delete, name="role_delete"),
    # Páginas bloqueadas: acción especial
    path("paginas-bloqueadas/<int:pk>/bloquear/", views.gate_lock, name="gate_lock"),
    # Recursos genéricos
    path("<resource:key>/", views.resource_list, name="resource_list"),
    path("<resource:key>/nuevo/", views.resource_form, name="resource_create"),
    path("<resource:key>/<int:pk>/", views.resource_form, name="resource_edit"),
    path("<resource:key>/<int:pk>/eliminar/", views.resource_delete, name="resource_delete"),
]
