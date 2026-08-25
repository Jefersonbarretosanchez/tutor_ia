"""
Puente entre pylti1p3 y nuestros modelos / la configuración de Django.
"""

from pylti1p3.contrib.django import DjangoCacheDataStorage, DjangoDbToolConf

# Claims estándar de LTI 1.3 que nos interesan.
CLAIM_DEPLOYMENT_ID = "https://purl.imsglobal.org/spec/lti/claim/deployment_id"
CLAIM_CONTEXT = "https://purl.imsglobal.org/spec/lti/claim/context"
CLAIM_ROLES = "https://purl.imsglobal.org/spec/lti/claim/roles"
CLAIM_CUSTOM = "https://purl.imsglobal.org/spec/lti/claim/custom"
CLAIM_AGS_ENDPOINT = "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint"

INSTRUCTOR_ROLE_MARKERS = ("Instructor", "ContentDeveloper", "Administrator")


def get_tool_conf():
    """Instancia el ToolConf respaldado por los modelos LtiTool/LtiToolKey."""
    return DjangoDbToolConf()


def get_launch_data_storage():
    """
    Guarda el estado del login OIDC (nonce/state) en el cache de Django en
    vez de en la sesión: los navegadores restringen cookies de terceros
    dentro del iframe de Canvas, y el cache (Redis en producción) no
    depende de eso.
    """
    return DjangoCacheDataStorage()


def is_instructor(launch_data: dict) -> bool:
    roles = launch_data.get(CLAIM_ROLES, []) or []
    return any(marker in role for role in roles for marker in INSTRUCTOR_ROLE_MARKERS)


def extract_course_fields(launch_data: dict) -> dict:
    context = launch_data.get(CLAIM_CONTEXT, {}) or {}
    custom = launch_data.get(CLAIM_CUSTOM, {}) or {}
    ags = launch_data.get(CLAIM_AGS_ENDPOINT, {}) or {}
    return {
        "deployment_id": launch_data.get(CLAIM_DEPLOYMENT_ID, ""),
        "context_id": context.get("id", ""),
        "title": context.get("title") or context.get("label") or "",
        "canvas_course_id": custom.get("canvas_course_id", ""),
        "ags_lineitems_url": ags.get("lineitems", ""),
        "ags_scope": ags.get("scope", []),
    }


def extract_student_fields(launch_data: dict) -> dict:
    custom = launch_data.get(CLAIM_CUSTOM, {}) or {}
    return {
        "deployment_id": launch_data.get(CLAIM_DEPLOYMENT_ID, ""),
        "sub": launch_data.get("sub", ""),
        "canvas_user_id": custom.get("canvas_user_id", ""),
        "login_id": custom.get("canvas_user_login_id", ""),
        "name": launch_data.get("name", ""),
        "email": launch_data.get("email", ""),
    }


def extract_enrollment_fields(launch_data: dict) -> dict:
    custom = launch_data.get(CLAIM_CUSTOM, {}) or {}
    return {
        "section_ids": custom.get("canvas_course_section_ids", ""),
    }
