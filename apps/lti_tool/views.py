import logging

from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from pylti1p3.contrib.django import DjangoMessageLaunch, DjangoOIDCLogin
from pylti1p3.exception import LtiException

from apps.chat.auth import encode_launch_token
from apps.chat.services import token_ledger
from apps.lti_tool.lti_config import (
    extract_course_fields,
    extract_enrollment_fields,
    extract_student_fields,
    get_launch_data_storage,
    get_tool_conf,
    is_instructor,
)
from apps.lti_tool.models import Course, CourseEnrollment, LtiLaunchLog, Student

logger = logging.getLogger(__name__)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@csrf_exempt
def login(request):
    """Paso 1 del OIDC third-party initiated login: Canvas redirige aquí antes del launch."""
    tool_conf = get_tool_conf()
    launch_data_storage = get_launch_data_storage()
    oidc_login = DjangoOIDCLogin(request, tool_conf, launch_data_storage=launch_data_storage)

    target_link_uri = request.GET.get("target_link_uri") or request.POST.get("target_link_uri")
    if not target_link_uri:
        return HttpResponseBadRequest("Falta el parámetro 'target_link_uri'.")

    return oidc_login.enable_check_cookies().redirect(target_link_uri)


@csrf_exempt
def launch(request):
    """
    Paso 2: Canvas hace POST con el id_token firmado. Aquí se valida,
    se resuelven/crean Course + Student + CourseEnrollment, y se sirve la
    página que embebe el widget de chat con un token corto de la API.
    """
    tool_conf = get_tool_conf()
    launch_data_storage = get_launch_data_storage()
    message_launch = DjangoMessageLaunch(request, tool_conf, launch_data_storage=launch_data_storage)

    try:
        launch_data = message_launch.get_launch_data()
    except LtiException as exc:
        logger.warning("LTI launch inválido: %s", exc)
        LtiLaunchLog.objects.create(
            issuer=request.POST.get("iss", ""),
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
            validated=False,
            error=str(exc),
        )
        return render(request, "lti_tool/launch_error.html", {"error": str(exc)}, status=400)

    course_fields = extract_course_fields(launch_data)
    student_fields = extract_student_fields(launch_data)

    if not course_fields["context_id"] or not student_fields["sub"]:
        error = "El lanzamiento no trae 'context.id' o 'sub' — revisa los claims habilitados en el Developer Key."
        LtiLaunchLog.objects.create(
            issuer=launch_data.get("iss", ""),
            client_id=launch_data.get("aud", ""),
            sub=student_fields["sub"],
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
            validated=False,
            error=error,
        )
        return render(request, "lti_tool/launch_error.html", {"error": error}, status=400)

    # El registro del LtiTool (issuer/client_id/deployment) lo resuelve
    # pylti1p3 internamente; aquí solo necesitamos identificarlo para
    # nuestras propias tablas. La forma más simple y estable: buscarlo por
    # (issuer, client_id) — ambos vienen en el propio launch_data.
    from pylti1p3.contrib.django.lti1p3_tool_config.models import LtiTool

    lti_tool_row = LtiTool.objects.get(issuer=launch_data.get("iss"), client_id=launch_data.get("aud"))

    course, _ = Course.objects.update_or_create(
        lti_tool=lti_tool_row,
        deployment_id=course_fields["deployment_id"],
        context_id=course_fields["context_id"],
        defaults={
            "title": course_fields["title"],
            "canvas_course_id": course_fields["canvas_course_id"],
            "ags_lineitems_url": course_fields["ags_lineitems_url"],
            "ags_scope": course_fields["ags_scope"],
        },
    )

    student, _ = Student.objects.update_or_create(
        lti_tool=lti_tool_row,
        deployment_id=student_fields["deployment_id"],
        sub=student_fields["sub"],
        defaults={
            "canvas_user_id": student_fields["canvas_user_id"],
            "login_id": student_fields["login_id"],
            "name": student_fields["name"],
            "email": student_fields["email"],
        },
    )

    enrollment, _ = CourseEnrollment.objects.update_or_create(
        student=student,
        course=course,
        defaults={
            "is_instructor": is_instructor(launch_data),
            **extract_enrollment_fields(launch_data),
        },
    )

    LtiLaunchLog.objects.create(
        lti_tool=lti_tool_row,
        issuer=launch_data.get("iss", ""),
        client_id=launch_data.get("aud", ""),
        sub=student.sub,
        ip_address=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
        validated=True,
    )

    token = encode_launch_token(enrollment)
    usage = token_ledger.get_usage_status(enrollment)

    return render(
        request,
        "lti_tool/chat_frame.html",
        {
            "launch_token": token,
            "api_base": "/api/",
            "course_title": course.title or course.context_id,
            "usage": usage.as_dict(),
        },
    )


def jwks(request):
    """JWKS público de la herramienta — se configura en el Developer Key de Canvas."""
    tool_conf = get_tool_conf()
    return JsonResponse(tool_conf.get_jwks())
