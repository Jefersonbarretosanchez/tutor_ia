"""
Nota de completitud al gradebook de Canvas vía LTI Assignment and Grade
Services (AGS) — se dispara cuando el agente de n8n marca la conversación
como "completed" (ver apps/chat/services/n8n_client.py).

Usa un único line item por curso (identificado por su "tag"), reusado
entre todos los estudiantes: no es una nota por plantilla/momento, sino
"completó la actividad del Tutor IA en este curso" — completo/incompleto.
"""

import logging

from django.utils import timezone
from pylti1p3.assignments_grades import AssignmentsGradesService
from pylti1p3.contrib.django.lti1p3_tool_config import DjangoDbToolConf
from pylti1p3.exception import LtiException
from pylti1p3.grade import Grade
from pylti1p3.lineitem import LineItem
from pylti1p3.service_connector import ServiceConnector

logger = logging.getLogger(__name__)

LINEITEM_TAG = "tutor_ia_actividad"
LINEITEM_LABEL = "Tutor IA — Actividad"


def _ags_service_for_course(course):
    lti_tool = course.lti_tool
    tool_conf = DjangoDbToolConf()
    registration = tool_conf.find_registration_by_params(lti_tool.issuer, lti_tool.client_id)
    connector = ServiceConnector(registration)
    service_data = {"scope": course.ags_scope or [], "lineitems": course.ags_lineitems_url}
    return AssignmentsGradesService(connector, service_data)


def _get_or_create_lineitem_url(course):
    if course.ags_lineitem_url:
        return course.ags_lineitem_url

    ags = _ags_service_for_course(course)
    new_lineitem = LineItem().set_tag(LINEITEM_TAG).set_label(LINEITEM_LABEL).set_score_maximum(1)
    lineitem = ags.find_or_create_lineitem(new_lineitem, find_by="tag")
    course.ags_lineitem_url = lineitem.get_id()
    course.save(update_fields=["ags_lineitem_url"])
    return course.ags_lineitem_url


def mark_activity_completed(enrollment) -> bool:
    """
    Manda 100% (completo/incompleto) a Canvas para este estudiante. Nunca
    propaga la excepción hacia arriba — un fallo de AGS no debe romper la
    respuesta del chat, solo queda logueado para revisar en /admin/.
    """
    course = enrollment.course
    student = enrollment.student

    if not course.ags_lineitems_url:
        logger.warning(
            "AGS: curso %s no tiene 'ags_lineitems_url' — falta habilitar los scopes de AGS "
            "en el Developer Key y relanzar la herramienta.",
            course,
        )
        return False

    try:
        lineitem_url = _get_or_create_lineitem_url(course)
        ags = _ags_service_for_course(course)
        grade = (
            Grade()
            .set_score_given(1)
            .set_score_maximum(1)
            .set_activity_progress("Completed")
            .set_grading_progress("FullyGraded")
            .set_timestamp(timezone.now().isoformat())
            .set_user_id(student.sub)
        )
        ags.put_grade(grade, LineItem().set_id(lineitem_url))
    except LtiException:
        logger.exception("AGS: fallo enviando nota para %s en curso %s", student, course)
        return False
    except Exception:
        logger.exception("AGS: fallo inesperado enviando nota para %s en curso %s", student, course)
        return False

    enrollment.graded_at = timezone.now()
    enrollment.save(update_fields=["graded_at"])
    logger.info("AGS: nota enviada para %s en curso %s", student, course)
    return True
