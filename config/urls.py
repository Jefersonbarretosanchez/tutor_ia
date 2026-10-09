from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # La raíz del dominio lleva al portal (si no hay sesión, al login). /admin/ sigue activo pero no se enlaza desde ningún lado.
    path("", RedirectView.as_view(pattern_name="portal:dashboard", permanent=False)),
    path("admin/", admin.site.urls),
    path("portal/", include("apps.portal.urls")),
    path("lti/", include("apps.lti_tool.urls")),
    path("api/", include("apps.chat.urls")),
]
