from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Obliga a cambiar la contraseña inicial/restablecida antes de usar el portal."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and request.path.startswith("/portal/"):
            ur = getattr(user, "portal_role", None)
            if ur is not None and ur.must_change_password:
                allowed = {reverse("portal:password_change"), reverse("portal:logout")}
                if request.path not in allowed:
                    return redirect("portal:password_change")
        return self.get_response(request)
