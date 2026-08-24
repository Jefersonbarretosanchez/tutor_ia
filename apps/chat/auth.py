"""
Autenticación del widget de chat dentro del iframe.

El chat vive en un <iframe> de origen cruzado dentro de Canvas. No podemos
depender de la cookie de sesión de Django para autenticar las llamadas a
la API (los navegadores restringen cada vez más las cookies de terceros).
En su lugar: tras validar el lanzamiento LTI, emitimos un token firmado y
de corta duración que el frontend guarda en memoria y manda como
`Authorization: Bearer <token>` en cada llamada.

Se usa `django.core.signing` (HMAC sobre SECRET_KEY/LAUNCH_TOKEN_SECRET,
con expiración) en vez de JWT: es un token puramente interno, no necesita
interoperar con nada externo, y así evitamos una dependencia extra.
"""

from django.conf import settings
from django.core import signing
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.lti_tool.models import CourseEnrollment

SALT = "lti-chat.launch-token"


def _signer():
    return signing.TimestampSigner(key=settings.LAUNCH_TOKEN_SECRET, salt=SALT)


def encode_launch_token(enrollment: CourseEnrollment) -> str:
    payload = signing.dumps({"enrollment_id": enrollment.pk}, key=settings.LAUNCH_TOKEN_SECRET, salt=SALT)
    return payload


def decode_launch_token(token: str) -> CourseEnrollment:
    try:
        data = signing.loads(
            token,
            key=settings.LAUNCH_TOKEN_SECRET,
            salt=SALT,
            max_age=settings.LAUNCH_TOKEN_TTL_SECONDS,
        )
    except signing.SignatureExpired as exc:
        raise AuthenticationFailed("La sesión del chat expiró. Recarga la página del curso en Canvas.") from exc
    except signing.BadSignature as exc:
        raise AuthenticationFailed("Token de sesión inválido.") from exc

    try:
        return CourseEnrollment.objects.select_related("student", "course").get(pk=data["enrollment_id"])
    except CourseEnrollment.DoesNotExist as exc:
        raise AuthenticationFailed("La matrícula asociada a este token ya no existe.") from exc


class _EnrollmentPrincipal:
    """Envoltorio mínimo para que DRF (IsAuthenticated) acepte la matrícula como 'usuario'."""

    is_authenticated = True

    def __init__(self, enrollment: CourseEnrollment):
        self.enrollment = enrollment

    def __str__(self):
        return str(self.enrollment)


class LaunchTokenAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith(f"{self.keyword} "):
            return None
        token = header[len(self.keyword) + 1 :].strip()
        if not token:
            return None
        enrollment = decode_launch_token(token)
        return (_EnrollmentPrincipal(enrollment), token)
