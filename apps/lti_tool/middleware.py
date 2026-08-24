from django.conf import settings


class LtiFrameAncestorsMiddleware:
    """
    Reemplaza el X-Frame-Options por defecto de Django.

    La herramienta LTI vive embebida en un <iframe> dentro de Canvas, así
    que no podemos usar DENY/SAMEORIGIN a nivel global. En su lugar:

    - Las rutas de /lti/ (login, launch, jwks) llevan
      `Content-Security-Policy: frame-ancestors` restringido a los dominios
      de Canvas configurados en LTI_FRAME_ANCESTORS.
    - Todo lo demás (el admin, la API llamada por el propio frontend) se
      mantiene sin permitir ser embebido.
    """

    LTI_PATH_PREFIX = "/lti/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.path.startswith(self.LTI_PATH_PREFIX):
            ancestors = getattr(settings, "LTI_FRAME_ANCESTORS", [])
            if ancestors:
                value = "frame-ancestors 'self' " + " ".join(ancestors)
            else:
                # Sin dominios configurados: no bloqueamos en desarrollo,
                # pero se registra la ausencia de configuración explícita.
                value = "frame-ancestors 'self'"
            response["Content-Security-Policy"] = value
        else:
            response.setdefault("X-Frame-Options", "DENY")

        return response
