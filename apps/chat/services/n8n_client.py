"""
Cliente HTTP hacia el webhook maestro de n8n (p. ej. WF3 · Clara).

Implementa el contrato acordado en el documento de alcance (sección 6):
Django autentica con un header propio, manda el historial reciente en el
payload (para que n8n no tenga que consultar nada para tener contexto), y
espera de vuelta el desglose de tokens del LLM.
"""

import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class N8nError(Exception):
    """Cualquier fallo hablando con n8n: timeout, HTTP >=400, o respuesta con forma inesperada."""


def call_flow(flow, *, user_id: str, course_id: str, momento_tipo: str, message: str, session_id: str, history: list) -> dict:
    """
    Llama al webhook de `flow` (un apps.chat.models.N8nFlow) y devuelve un
    dict normalizado: {"reply": str, "tokens": {"prompt", "completion", "total"}, "execution_id": str}.

    Lanza N8nError si algo sale mal — el llamador decide cómo responderle
    al estudiante (nunca se descuentan tokens si esto falla).
    """
    payload = {
        "user_id": user_id,
        "course_id": course_id,
        "momento_tipo": momento_tipo,
        "message": message,
        "session_id": str(session_id),
        "history": history,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Token": flow.shared_secret,
    }

    started = time.monotonic()
    try:
        response = requests.post(
            flow.webhook_url,
            json=payload,
            headers=headers,
            timeout=flow.timeout_seconds or settings.N8N_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.error("n8n: fallo de red llamando a %s (%s): %s", flow.code, flow.webhook_url, exc)
        raise N8nError(f"No se pudo contactar al agente ({flow.code}).") from exc

    latency_ms = int((time.monotonic() - started) * 1000)

    if response.status_code >= 400:
        logger.error("n8n: %s respondió %s: %s", flow.code, response.status_code, response.text[:500])
        raise N8nError(f"El agente ({flow.code}) respondió con un error ({response.status_code}).")

    try:
        data = response.json()
    except ValueError as exc:
        raise N8nError(f"El agente ({flow.code}) devolvió una respuesta que no es JSON válido.") from exc

    reply = data.get("reply")
    if not reply:
        raise N8nError(f"El agente ({flow.code}) no devolvió el campo 'reply'.")

    tokens = data.get("tokens") or {}
    # Compatibilidad con la forma actual de /clara (un único "tokens_used")
    # mientras se aplica el cambio descrito en la sección 6 del alcance.
    if not tokens and "tokens_used" in data:
        tokens = {"prompt": 0, "completion": 0, "total": int(data.get("tokens_used") or 0)}

    normalized = {
        "reply": reply,
        "tokens": {
            "prompt": int(tokens.get("prompt", 0) or 0),
            "completion": int(tokens.get("completion", 0) or 0),
            "total": int(tokens.get("total", 0) or 0),
        },
        "execution_id": data.get("execution_id", ""),
        "latency_ms": latency_ms,
    }
    return normalized
