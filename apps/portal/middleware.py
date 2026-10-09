from django.shortcuts import redirect
from django.urls import reverse
from django.utils.cache import patch_vary_headers


class PortalMiddleware:
    """
    - Obliga a cambiar la contraseña inicial/restablecida antes de usar el portal.
    - Marca `Vary: HX-Request`: la misma URL devuelve página completa o fragmento (HTMX),
      y el navegador no debe mezclarlas en su caché.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/portal/"):
            return self.get_response(request)

        user = request.user
        if user.is_authenticated:
            ur = getattr(user, "portal_role", None)
            if ur is not None and ur.must_change_password:
                allowed = {reverse("portal:password_change"), reverse("portal:logout")}
                if request.path not in allowed:
                    return redirect("portal:password_change")

        response = self.get_response(request)
        patch_vary_headers(response, ["HX-Request"])
        return response
