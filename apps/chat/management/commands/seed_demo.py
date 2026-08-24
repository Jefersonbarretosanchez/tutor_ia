"""
Datos de ejemplo para probar la API del chat SIN pasar por un lanzamiento
real de Canvas. Crea una plataforma/curso/estudiante ficticios y un
N8nFlow apuntando al webhook /clara descrito en el documento de alcance,
e imprime un token de sesión listo para usar con curl.

Uso:
    python manage.py seed_demo --n8n-webhook-url https://tu-n8n/webhook/clara --n8n-secret ****
"""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.management.base import BaseCommand
from pylti1p3.contrib.django.lti1p3_tool_config.models import LtiTool, LtiToolKey

from apps.chat.auth import encode_launch_token
from apps.chat.models import N8nFlow, PromptTemplate
from apps.lti_tool.models import Course, CourseEnrollment, Student

DEMO_ISSUER = "https://canvas-demo.instructure.com"
DEMO_CLIENT_ID = "demo-client-id"
DEMO_DEPLOYMENT_ID = "demo-deployment-1"


class Command(BaseCommand):
    help = "Crea datos de ejemplo (curso, estudiante, plantillas) y emite un token de sesión para probar la API."

    def add_arguments(self, parser):
        parser.add_argument("--n8n-webhook-url", default="https://CAMBIA-ESTO.app.n8n.cloud/webhook/clara")
        parser.add_argument("--n8n-secret", default="cambia-este-secreto")

    def handle(self, *args, **options):
        key, created = LtiToolKey.objects.get_or_create(name="demo-key")
        if created or not key.private_key:
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            key.private_key = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode()
            key.public_key = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode()
            key.save()

        lti_tool, _ = LtiTool.objects.get_or_create(
            issuer=DEMO_ISSUER,
            client_id=DEMO_CLIENT_ID,
            defaults={
                "title": "Canvas de prueba",
                "auth_login_url": f"{DEMO_ISSUER}/api/lti/authorize_redirect",
                "auth_token_url": f"{DEMO_ISSUER}/login/oauth2/token",
                "key_set_url": f"{DEMO_ISSUER}/api/lti/security/jwks",
                "deployment_ids": f'["{DEMO_DEPLOYMENT_ID}"]',
                "tool_key": key,
            },
        )

        course, _ = Course.objects.get_or_create(
            lti_tool=lti_tool,
            deployment_id=DEMO_DEPLOYMENT_ID,
            context_id="demo-course-1",
            defaults={"title": "Curso de demostración", "canvas_course_id": "4821"},
        )

        student, _ = Student.objects.get_or_create(
            lti_tool=lti_tool,
            deployment_id=DEMO_DEPLOYMENT_ID,
            sub="demo-student-sub-1",
            defaults={"canvas_user_id": "1193"},
        )

        enrollment, _ = CourseEnrollment.objects.get_or_create(student=student, course=course)

        flow, _ = N8nFlow.objects.get_or_create(
            code="WF3_CLARA",
            defaults={
                "label": "WF3 — Clara Tutor IA",
                "webhook_url": options["n8n_webhook_url"],
                "shared_secret": options["n8n_secret"],
            },
        )

        for momento, title in [
            (PromptTemplate.MOMENTO_BIENVENIDA, "Empezar el módulo"),
            (PromptTemplate.MOMENTO_LIBRE, "Resolver una duda"),
            (PromptTemplate.MOMENTO_CIERRE, "Repasar antes del cierre"),
        ]:
            PromptTemplate.objects.get_or_create(
                course=course,
                momento_tipo=momento,
                defaults={"title": title, "n8n_flow": flow},
            )

        token = encode_launch_token(enrollment)

        self.stdout.write(self.style.SUCCESS("Datos de ejemplo listos."))
        self.stdout.write(f"Course: {course}  |  Student: {student}  |  Enrollment: {enrollment.pk}")
        self.stdout.write("")
        self.stdout.write("Token de sesión (usar como 'Authorization: Bearer <token>'):")
        self.stdout.write(token)
        self.stdout.write("")
        self.stdout.write("Prueba rápida:")
        self.stdout.write(
            f'  curl -H "Authorization: Bearer {token}" http://127.0.0.1:8000/api/templates/'
        )
