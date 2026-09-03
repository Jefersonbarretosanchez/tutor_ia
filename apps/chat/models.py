from django.db import models
from django.db.models import Sum


class N8nFlow(models.Model):
    """Un webhook de n8n invocable como 'agente maestro' (p. ej. WF3 · Clara)."""

    code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Identificador interno, p. ej. WF3_CLARA.",
    )
    label = models.CharField(max_length=255)
    webhook_url = models.URLField(help_text="URL del webhook de producción en n8n.")
    shared_secret = models.CharField(
        max_length=255,
        help_text="Valor enviado en el header X-Internal-Token — debe coincidir con el que valida el workflow en n8n.",
    )
    timeout_seconds = models.PositiveIntegerField(default=40)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} — {self.label}"


class PromptTemplate(models.Model):
    """
    La 'plantilla sugerida' que ve el estudiante al abrir el chat.

    Reutiliza el concepto de `momento_tipo` que ya existe en el workflow de
    n8n (WF3 · Clara): bienvenida / diagnostico / cierre / libre. Django no
    inventa un mecanismo nuevo, solo decide cuál mostrar por curso y con
    qué copy.
    """

    MOMENTO_BIENVENIDA = "bienvenida"
    MOMENTO_DIAGNOSTICO = "diagnostico"
    MOMENTO_CIERRE = "cierre"
    MOMENTO_LIBRE = "libre"
    MOMENTO_CHOICES = [
        (MOMENTO_BIENVENIDA, "Bienvenida"),
        (MOMENTO_DIAGNOSTICO, "Diagnóstico"),
        (MOMENTO_CIERRE, "Cierre de curso"),
        (MOMENTO_LIBRE, "Conversación libre"),
    ]

    course = models.ForeignKey(
        "lti_tool.Course",
        on_delete=models.CASCADE,
        related_name="templates",
        null=True,
        blank=True,
        help_text="Vacío = plantilla global, disponible en cualquier curso.",
    )
    momento_tipo = models.CharField(max_length=20, choices=MOMENTO_CHOICES, default=MOMENTO_LIBRE)
    title = models.CharField(max_length=255, help_text="Texto que ve el estudiante, p. ej. 'Resolver dudas del módulo 3'.")
    description = models.TextField(blank=True)
    n8n_flow = models.ForeignKey(N8nFlow, on_delete=models.PROTECT, related_name="templates")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return self.title


class ChatSession(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_LIMITED = "limited"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Activa"),
        (STATUS_LIMITED, "Límite alcanzado"),
        (STATUS_CLOSED, "Cerrada"),
    ]

    enrollment = models.ForeignKey(
        "lti_tool.CourseEnrollment",
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )
    template = models.ForeignKey(PromptTemplate, on_delete=models.PROTECT, related_name="sessions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_activity_at"]

    def __str__(self):
        return f"Sesión #{self.pk} — {self.enrollment}"


class ChatMessage(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_SYSTEM = "system"
    ROLE_CHOICES = [
        (ROLE_USER, "Estudiante"),
        (ROLE_ASSISTANT, "Agente"),
        (ROLE_SYSTEM, "Sistema"),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    tokens_prompt = models.PositiveIntegerField(default=0)
    tokens_completion = models.PositiveIntegerField(default=0)
    tokens_total = models.PositiveIntegerField(default=0)
    n8n_execution_id = models.CharField(max_length=255, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] {self.content[:40]}"


class ClaraMoment(models.Model):
    """
    Estado del flujo de apertura/conversación de Clara (webhooks n8n
    `/clara/apertura` y `/clara/responder`) para un estudiante en un
    momento puntual del curso (una unidad/página, identificada por el
    Custom Parameter LTI `momento` configurado en esa página de Canvas).

    Un único registro por (enrollment, momento): la pregunta de apertura y
    el historial no se vuelven a pedir al webhook si el estudiante ya
    tiene uno para esa página — solo se recupera lo ya guardado.
    """

    MOMENTO_BIENVENIDA = "bienvenida"
    MOMENTO_UNIDAD_1 = "unidad_1"
    MOMENTO_UNIDAD_2 = "unidad_2"
    MOMENTO_CIERRE = "cierre"
    MOMENTO_CHOICES = [
        (MOMENTO_BIENVENIDA, "Bienvenida"),
        (MOMENTO_UNIDAD_1, "Unidad 1"),
        (MOMENTO_UNIDAD_2, "Unidad 2"),
        (MOMENTO_CIERRE, "Cierre de curso"),
    ]

    enrollment = models.ForeignKey(
        "lti_tool.CourseEnrollment",
        on_delete=models.CASCADE,
        related_name="clara_moments",
    )
    momento = models.CharField(max_length=20, choices=MOMENTO_CHOICES)
    pregunta_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Id de la pregunta detonadora en Supabase (campo 'pregunta_id' de /clara/apertura).",
    )
    mensajes_usados = models.PositiveIntegerField(default=0)
    limite = models.PositiveIntegerField(
        default=8,
        help_text="Campo 'limite' que reporta n8n — hoy vestigial, el presupuesto real es por tokens (ver abajo).",
    )
    tokens_used = models.PositiveIntegerField(
        default=0,
        help_text="Campo 'tokens_usados' (acumulado) que reporta n8n para este momento — no es un conteo propio de Django.",
    )
    presupuesto = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Presupuesto de tokens de la unidad, tal como lo reporta n8n (campo 'presupuesto'). Vacío hasta el primer turno real.",
    )
    porcentaje_usado = models.PositiveIntegerField(
        default=0,
        help_text="Porcentaje de presupuesto consumido, tal como lo reporta n8n (campo 'porcentaje_usado') — controla la barra de progreso.",
    )
    puede_avanzar = models.BooleanField(default=False)
    page_unlocked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Cuándo se agregó al estudiante al 'Asignar acceso' de la página de Canvas "
            "configurada para este momento (ver lti_tool.CoursePageGate). Vacío = todavía no."
        ),
    )
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("enrollment", "momento")]
        ordering = ["-last_activity_at"]

    def __str__(self):
        return f"{self.enrollment} · {self.momento}"


class ClaraMessage(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [
        (ROLE_USER, "Estudiante"),
        (ROLE_ASSISTANT, "Clara"),
    ]

    moment = models.ForeignKey(ClaraMoment, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    tokens_used = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] {self.content[:40]}"


class TokenUsageLedger(models.Model):
    """
    Registro append-only del consumo de tokens. Nunca se actualiza ni se
    borra una fila: el consumo acumulado de un estudiante en un curso es
    siempre la suma de su ledger, nunca un contador mutable.
    """

    enrollment = models.ForeignKey(
        "lti_tool.CourseEnrollment",
        on_delete=models.CASCADE,
        related_name="token_ledger",
    )
    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )
    tokens_total = models.IntegerField(help_text="Puede ser negativo para ajustes manuales de crédito.")
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.enrollment} · {self.tokens_total:+d} tokens"

    @classmethod
    def total_for(cls, enrollment) -> int:
        return cls.objects.filter(enrollment=enrollment).aggregate(total=Sum("tokens_total"))["total"] or 0
