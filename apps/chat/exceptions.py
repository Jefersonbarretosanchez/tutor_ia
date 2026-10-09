from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.chat.services.clara_client import ClaraError

# Mensaje que ve el estudiante cuando falla el agente (Clara/n8n). El detalle
# técnico real (URL, status code, respuesta cruda) ya queda registrado por
# los logger.error() de clara_client.py — no tiene sentido
# mostrárselo al estudiante, solo generaría alarma sin que pueda hacer nada
# con esa información.
AGENT_ERROR_MESSAGE = "Tuvimos una falla respondiendo. Intenta de nuevo en un momento."


def chat_exception_handler(exc, context):
    """Convierte ClaraError (y cualquier otra excepción no manejada) en un JSON amigable."""
    if isinstance(exc, ClaraError):
        return Response({"error": AGENT_ERROR_MESSAGE, "code": "clara_error"}, status=502)

    response = exception_handler(exc, context)
    return response
