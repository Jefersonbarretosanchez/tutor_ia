from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.chat.services.clara_client import ClaraError
from apps.chat.services.n8n_client import N8nError

# Mensaje que ve el estudiante cuando falla el agente (n8n/Clara). El detalle
# técnico real (URL, status code, respuesta cruda) ya queda registrado por
# los logger.error() de n8n_client.py/clara_client.py — no tiene sentido
# mostrárselo al estudiante, solo generaría alarma sin que pueda hacer nada
# con esa información.
AGENT_ERROR_MESSAGE = "Tuvimos una falla respondiendo. Intenta de nuevo en un momento."


def chat_exception_handler(exc, context):
    """Convierte N8nError/ClaraError (y cualquier otra excepción no manejada) en un JSON amigable."""
    if isinstance(exc, (ClaraError, N8nError)):
        code = "clara_error" if isinstance(exc, ClaraError) else "n8n_error"
        return Response({"error": AGENT_ERROR_MESSAGE, "code": code}, status=502)

    response = exception_handler(exc, context)
    return response
