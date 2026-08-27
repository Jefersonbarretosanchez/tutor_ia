"""
Modelos propios de la herramienta LTI.

El registro de plataformas (issuer, client_id, URLs de OIDC, JWKS y las
claves RSA de la herramienta) NO se reinventa aquí: lo provee el propio
paquete `pylti1p3` a través de `pylti1p3.contrib.django.lti1p3_tool_config`
(modelos `LtiTool` / `LtiToolKey`, con su propio admin y migraciones).

Lo que sí es específico de este proyecto es todo lo que cuelga de un
lanzamiento válido: el curso, el estudiante, su matrícula (con el
interruptor de "chat habilitado") y el registro de auditoría de cada
intento de lanzamiento.
"""

from django.db import models

LTI_TOOL_MODEL = "lti1p3_tool_config.LtiTool"


class Course(models.Model):
    """Un curso de Canvas, identificado por el `context` claim de LTI."""

    lti_tool = models.ForeignKey(
        LTI_TOOL_MODEL,
        on_delete=models.PROTECT,
        related_name="courses",
        help_text="Plataforma (Developer Key) desde la que se lanzó este curso.",
    )
    deployment_id = models.CharField(max_length=255)
    context_id = models.CharField(
        max_length=255,
        help_text="Claim estándar 'context.id' de LTI — es el identificador de curso de Canvas.",
    )
    canvas_course_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Opcional: 'custom_canvas_course_id' si el Developer Key lo expone.",
    )
    title = models.CharField(max_length=255, blank=True)
    ags_lineitems_url = models.CharField(
        max_length=1024,
        blank=True,
        help_text="Claim AGS 'endpoint.lineitems' — URL para crear/listar line items del curso.",
    )
    ags_lineitem_url = models.CharField(
        max_length=1024,
        blank=True,
        help_text="Line item ya creado/reusado para la actividad del Tutor IA en este curso.",
    )
    ags_scope = models.JSONField(
        default=list,
        blank=True,
        help_text="Scopes AGS otorgados por Canvas (claim 'endpoint.scope').",
    )
    token_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Límite de tokens por estudiante en este curso. Vacío = usar el valor por defecto global.",
    )
    show_unit_token_count = models.BooleanField(
        default=False,
        help_text=(
            "La barra de progreso de cada unidad siempre muestra el porcentaje de Clara. "
            "Marca esto para que además se le muestre al estudiante el número de tokens consumidos/presupuesto."
        ),
    )
    show_course_token_usage = models.BooleanField(
        default=True,
        help_text=(
            "Muestra en el chat cuántos tokens ha consumido el estudiante en total en este curso "
            "(un número, sin el límite configurado ni barra de progreso)."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("lti_tool", "deployment_id", "context_id")]
        ordering = ["title", "context_id"]

    def __str__(self):
        return self.title or self.context_id

    @property
    def effective_token_limit(self):
        from django.conf import settings

        return self.token_limit or settings.DEFAULT_COURSE_TOKEN_LIMIT


class Student(models.Model):
    """Un estudiante, identificado por el claim estándar `sub` de LTI."""

    lti_tool = models.ForeignKey(
        LTI_TOOL_MODEL,
        on_delete=models.PROTECT,
        related_name="students",
    )
    deployment_id = models.CharField(max_length=255)
    sub = models.CharField(
        max_length=255,
        help_text="Claim estándar 'sub' — identificador opaco y estable del usuario en esa plataforma.",
    )
    canvas_user_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Opcional: 'custom_canvas_user_id' si el Developer Key lo expone.",
    )
    login_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Usuario institucional ('custom_canvas_user_login_id') si el Developer Key lo expone.",
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Claim estándar 'name' — requiere Privacy Level 'Public' en el Developer Key.",
    )
    email = models.EmailField(
        blank=True,
        help_text="Claim estándar 'email' — requiere Privacy Level 'Public' (o 'Email only') en el Developer Key.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("lti_tool", "deployment_id", "sub")]

    def __str__(self):
        return self.name or self.canvas_user_id or self.sub


class CourseEnrollment(models.Model):
    """Estado de un estudiante dentro de un curso puntual: aquí vive el interruptor de límite."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    is_instructor = models.BooleanField(
        default=False,
        help_text="Si el rol LTI incluye Instructor — pensado para eximir del límite de tokens.",
    )
    section_ids = models.CharField(
        max_length=255,
        blank=True,
        help_text="'custom_canvas_course_section_ids' si el Developer Key lo expone (separados por coma).",
    )
    chat_enabled = models.BooleanField(default=True)
    limit_reached_at = models.DateTimeField(null=True, blank=True)
    graded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Cuándo se envió la nota de completitud a Canvas (AGS). Vacío = todavía no.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("student", "course")]

    def __str__(self):
        return f"{self.student} @ {self.course}"


class LtiLaunchLog(models.Model):
    """Auditoría de cada intento de lanzamiento — se registra incluso si falla la validación."""

    lti_tool = models.ForeignKey(
        LTI_TOOL_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="launch_logs",
    )
    issuer = models.CharField(max_length=255, blank=True)
    client_id = models.CharField(max_length=255, blank=True)
    sub = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    validated = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        status = "OK" if self.validated else "ERROR"
        return f"[{status}] {self.issuer} sub={self.sub} — {self.created_at:%Y-%m-%d %H:%M}"
