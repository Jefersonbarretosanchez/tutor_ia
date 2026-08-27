from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.chat.services.clara_client import ClaraError
from apps.chat.services.n8n_client import N8nError


def chat_exception_handler(exc, context):
    """Convierte N8nError/ClaraError (y cualquier otra excepción no manejada) en un JSON amigable."""
    if isinstance(exc, ClaraError):
        return Response({"error": str(exc), "code": "clara_error"}, status=502)
    if isinstance(exc, N8nError):
        return Response({"error": str(exc), "code": "n8n_error"}, status=502)

    response = exception_handler(exc, context)
    return response
