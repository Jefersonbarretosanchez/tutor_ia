"""
Cliente HTTP hacia los webhooks fijos de Clara en n8n:
`/clara/apertura` (pregunta detonadora del momento) y `/clara/responder`
(turno de conversación).

A diferencia de apps.chat.services.n8n_client (webhook genérico
configurable por curso desde /admin/, vía N8nFlow/PromptTemplate), este es
un contrato cerrado y específico del workflow "Tutor IA (Clara)": sin
header de autenticación, y con un vocabulario fijo de `momento` (ver
apps.chat.models.ClaraMoment.MOMENTO_CHOICES).
"""

import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class ClaraError(Exception):
    """Cualquier fallo hablando con los webhooks de Clara: timeout, HTTP >=400, o respuesta con forma inesperada."""


def _post(url: str, payload: dict) -> dict:
    started = time.monotonic()
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=settings.CLARA_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.error("Clara: fallo de red llamando a %s: %s", url, exc)
        raise ClaraError("No se pudo contactar al tutor Clara.") from exc

    latency_ms = int((time.monotonic() - started) * 1000)

    if response.status_code >= 400:
        logger.error("Clara: %s respondió %s: %s", url, response.status_code, response.text[:500])
        raise ClaraError(f"Clara respondió con un error ({response.status_code}).")

    try:
        data = response.json()
    except ValueError as exc:
        logger.error("Clara: %s devolvió %s no-JSON: %s", url, response.status_code, response.text[:500])
        raise ClaraError("Clara devolvió una respuesta que no es JSON válido.") from exc

    if not data.get("reply"):
        raise ClaraError(f"Clara ({url}) no devolvió el campo 'reply'.")

    logger.debug("Clara: %s respondió en %dms", url, latency_ms)
    return data


def call_apertura(*, user_id: str, course_id: str, momento: str) -> dict:
    """Pide la pregunta detonadora de un momento. No consume tokens de LLM."""
    data = _post(
        settings.CLARA_APERTURA_URL,
        {"user_id": user_id, "course_id": course_id, "momento": momento},
    )
    return {
        "reply": data["reply"],
        "pregunta_id": str(data.get("pregunta_id") or ""),
        "mensajes_usados": int(data.get("mensajes_usados", 0) or 0),
        "limite": int(data.get("limite", 0) or 0),
        "tokens_used": int(data.get("tokens_used", 0) or 0),
    }


def call_responder(*, user_id: str, course_id: str, momento: str, message: str) -> dict:
    """Manda la respuesta del estudiante y devuelve el turno del agente (o el aviso de límite)."""
    data = _post(
        settings.CLARA_RESPONDER_URL,
        {"user_id": user_id, "course_id": course_id, "momento": momento, "message": message},
    )
    return {
        "reply": data["reply"],
        "tipo": data.get("tipo", "respuesta"),
        "puede_avanzar": bool(data.get("puede_avanzar", False)),
        "mensajes_usados": int(data.get("mensajes_usados", 0) or 0),
        "limite": int(data.get("limite", 0) or 0),
        "tokens_used": int(data.get("tokens_used", 0) or 0),
    }
