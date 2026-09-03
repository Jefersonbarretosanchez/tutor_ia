"""
Desbloqueo de páginas de Canvas por estudiante vía "Asignar acceso"
(assignment overrides), cuando `ClaraMoment.puede_avanzar` se vuelve True.

A diferencia de apps/chat/services/grades.py (LTI Advantage AGS, autenticado
con la registración LTI del Developer Key vía pylti1p3), esto es una llamada
directa al API REST de Canvas — requiere un token de acceso propio
(CANVAS_API_TOKEN) con permiso de edición de curso, gestionado aparte del
Developer Key LTI.

El mapeo de qué página desbloquear para cada `momento` vive en
lti_tool.CoursePageGate, configurable por curso desde /admin/.
"""

import logging
import re

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.lti_tool.models import CoursePageGate

logger = logging.getLogger(__name__)

OVERRIDE_TITLE = "tutor_ia_desbloqueo"

# Cualquier "/courses/<id>/external_tools/retrieve" embebido en el cuerpo de
# una página — es la URL que Canvas genera al insertar el chat vía "Apps" en
# el editor, y queda fija al curso en el que se insertó (ver
# fix_retrieve_course_ids: al duplicar el curso para una nueva cohorte, este
# número no se actualiza solo).
RETRIEVE_URL_RE = re.compile(r"/courses/(\d+)/external_tools/retrieve")


def _date_details_url(course, gate):
    return (
        f"{settings.CANVAS_API_BASE_URL}/api/v1/courses/{course.canvas_course_id}"
        f"/pages/{gate.canvas_page_url}/date_details"
    )


def _headers():
    return {"Authorization": f"Bearer {settings.CANVAS_API_TOKEN}"}


def unlock_page_for_student(moment) -> bool:
    """
    Agrega al estudiante de `moment` al override de la página configurada
    para su `momento` en este curso. Nunca propaga la excepción hacia
    arriba — un fallo del API de Canvas no debe romper la respuesta del
    chat, solo queda logueado para revisar.
    """
    enrollment = moment.enrollment
    course = enrollment.course
    student = enrollment.student

    gate = course.page_gates.filter(momento=moment.momento).first()
    if not gate:
        # Este momento no tiene página configurada todavía — no-op silencioso.
        return False

    if not course.canvas_course_id or not student.canvas_user_id:
        logger.warning(
            "Canvas pages: falta canvas_course_id/canvas_user_id para %s — "
            "revisa las Custom Variables del Developer Key.",
            enrollment,
        )
        return False

    url = _date_details_url(course, gate)

    try:
        with transaction.atomic():
            # select_for_update serializa el GET-modify-PUT de la misma
            # página entre estudiantes que completan casi al mismo tiempo.
            CoursePageGate.objects.select_for_update().get(pk=gate.pk)

            resp = requests.get(url, headers=_headers(), timeout=settings.CANVAS_API_TIMEOUT_SECONDS)
            resp.raise_for_status()
            current = resp.json()

            overrides = current.get("overrides") or []
            mine = next((o for o in overrides if o.get("title") == OVERRIDE_TITLE), None)
            student_ids = set(mine["student_ids"]) if mine else set()
            student_ids.add(int(student.canvas_user_id))

            override_payload = {"title": OVERRIDE_TITLE, "student_ids": sorted(student_ids)}
            if mine and mine.get("id"):
                override_payload["id"] = mine["id"]

            put_resp = requests.put(
                url,
                headers=_headers(),
                json={"only_visible_to_overrides": True, "assignment_overrides": [override_payload]},
                timeout=settings.CANVAS_API_TIMEOUT_SECONDS,
            )
            put_resp.raise_for_status()
    except requests.RequestException:
        logger.exception("Canvas pages: fallo desbloqueando %s para %s", gate.canvas_page_url, enrollment)
        return False
    except Exception:
        logger.exception(
            "Canvas pages: fallo inesperado desbloqueando %s para %s", gate.canvas_page_url, enrollment
        )
        return False

    moment.page_unlocked_at = timezone.now()
    moment.save(update_fields=["page_unlocked_at"])
    logger.info("Canvas pages: %s desbloqueó %s", enrollment, gate.canvas_page_url)
    return True


def lock_page(gate) -> bool:
    """
    Setup inicial de un CoursePageGate: deja la página oculta a todos
    (only_visible_to_overrides=true, sin overrides) hasta el primer
    desbloqueo real. Se llama una sola vez, desde la acción de /admin/.
    """
    course = gate.course
    if not course.canvas_course_id:
        logger.warning("Canvas pages: curso %s no tiene canvas_course_id — no se puede bloquear %s", course, gate)
        return False

    url = _date_details_url(course, gate)

    try:
        resp = requests.put(
            url,
            headers=_headers(),
            json={"only_visible_to_overrides": True, "assignment_overrides": []},
            timeout=settings.CANVAS_API_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.RequestException:
        logger.exception("Canvas pages: fallo bloqueando %s", gate.canvas_page_url)
        return False
    except Exception:
        logger.exception("Canvas pages: fallo inesperado bloqueando %s", gate.canvas_page_url)
        return False

    gate.locked_at = timezone.now()
    gate.save(update_fields=["locked_at"])
    logger.info("Canvas pages: %s bloqueada (only_visible_to_overrides)", gate.canvas_page_url)
    return True


def list_page_urls(course) -> list[str]:
    """Slugs ('url') de todas las páginas del curso, paginando la respuesta de Canvas."""
    slugs = []
    url = f"{settings.CANVAS_API_BASE_URL}/api/v1/courses/{course.canvas_course_id}/pages?per_page=100"
    while url:
        resp = requests.get(url, headers=_headers(), timeout=settings.CANVAS_API_TIMEOUT_SECONDS)
        resp.raise_for_status()
        slugs.extend(page["url"] for page in resp.json())
        url = resp.links.get("next", {}).get("url")
    return slugs


def find_stale_retrieve_urls(course, page_url: str) -> str | None:
    """
    Devuelve el cuerpo corregido de la página si contiene un embed
    "external_tools/retrieve" apuntando a un curso distinto de
    `course.canvas_course_id`; None si no hay nada que corregir.
    """
    detail_url = f"{settings.CANVAS_API_BASE_URL}/api/v1/courses/{course.canvas_course_id}/pages/{page_url}"
    resp = requests.get(detail_url, headers=_headers(), timeout=settings.CANVAS_API_TIMEOUT_SECONDS)
    resp.raise_for_status()
    body = resp.json().get("body") or ""

    stale_ids = {m for m in RETRIEVE_URL_RE.findall(body) if m != str(course.canvas_course_id)}
    if not stale_ids:
        return None

    fixed_body = RETRIEVE_URL_RE.sub(f"/courses/{course.canvas_course_id}/external_tools/retrieve", body)
    return fixed_body


def update_page_body(course, page_url: str, body: str) -> None:
    detail_url = f"{settings.CANVAS_API_BASE_URL}/api/v1/courses/{course.canvas_course_id}/pages/{page_url}"
    resp = requests.put(
        detail_url,
        headers=_headers(),
        json={"wiki_page": {"body": body}},
        timeout=settings.CANVAS_API_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
