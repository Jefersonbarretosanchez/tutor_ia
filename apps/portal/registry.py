"""
Recursos del portal gestionados por las vistas genéricas (listado + formulario).

Cada Resource enlaza un modelo existente con las columnas del listado, los
campos del formulario y la clave de permisos (ver permissions.CATALOG).
Las vistas con lógica propia (usuarios, roles, matrículas, conversaciones)
viven en views.py.
"""

from dataclasses import dataclass, field

from django import forms

from apps.chat.models import N8nFlow, PromptTemplate, TokenUsageLedger
from apps.lti_tool.models import Course, CoursePageGate, DefaultPageGate, LtiLaunchLog, Student

from .models import AuditLog


@dataclass
class Resource:
    key: str
    label: str
    model: type
    columns: list  # [(encabezado, atributo | callable(obj))]
    search: tuple = ()
    fields: list = field(default_factory=list)  # vacío = solo lectura
    select_related: tuple = ()
    can_create: bool = False
    can_delete: bool = False
    form_class: type = None
    extra_actions: tuple = ()  # (acción de permiso, url name, etiqueta)
    ordering: tuple = ()

    @property
    def readonly(self):
        return not self.fields


class FlowForm(forms.ModelForm):
    """El secreto nunca se muestra; vacío al editar = conservar el actual."""

    shared_secret = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        label="Secreto compartido (X-Internal-Token)",
        help_text="Déjalo vacío para conservar el actual.",
    )

    class Meta:
        model = N8nFlow
        fields = ["code", "label", "webhook_url", "shared_secret", "timeout_seconds", "is_active"]

    def clean_shared_secret(self):
        value = self.cleaned_data.get("shared_secret")
        if not value and not self.instance.pk:
            raise forms.ValidationError("Obligatorio al crear un flujo.")
        return value or self.instance.shared_secret


def _bool(attr):
    return lambda o: "Sí" if getattr(o, attr) else "No"


RESOURCES = {
    r.key: r
    for r in [
        Resource(
            "courses", "Cursos", Course,
            columns=[
                ("Título", lambda o: o.title or o.context_id),
                ("Context ID", "context_id"),
                ("Límite tokens", lambda o: o.effective_token_limit),
                ("Activo", _bool("is_active")),
                ("AGS", lambda o: "Sí" if o.ags_lineitems_url else "No"),
            ],
            search=("title", "context_id", "canvas_course_id"),
            fields=["title", "token_limit", "show_unit_token_count", "show_course_token_usage", "is_active"],
        ),
        Resource(
            "gates", "Páginas gate por curso", CoursePageGate,
            columns=[
                ("Curso", "course"), ("Momento", "momento"), ("Página Canvas", "canvas_page_url"),
                ("Etiqueta", "label"), ("Orden", "order"),
                ("Bloqueada", lambda o: o.locked_at.strftime("%Y-%m-%d %H:%M") if o.locked_at else "No"),
            ],
            search=("canvas_page_url", "momento", "label", "course__title"),
            fields=["course", "momento", "canvas_page_url", "label", "icon", "order"],
            select_related=("course",), can_create=True, can_delete=True,
            extra_actions=(("lock", "portal:gate_lock", "Bloquear en Canvas"),),
        ),
        Resource(
            "default_gates", "Gates por defecto", DefaultPageGate,
            columns=[("Momento", "momento"), ("Página Canvas", "canvas_page_url"), ("Etiqueta", "label"), ("Orden", "order")],
            search=("canvas_page_url", "momento", "label"),
            fields=["momento", "canvas_page_url", "label", "icon", "order"],
            can_create=True, can_delete=True,
        ),
        Resource(
            "flows", "Flujos n8n", N8nFlow,
            columns=[("Código", "code"), ("Nombre", "label"), ("Webhook", "webhook_url"), ("Timeout (s)", "timeout_seconds"), ("Activo", _bool("is_active"))],
            search=("code", "label"),
            fields=["code", "label", "webhook_url", "shared_secret", "timeout_seconds", "is_active"],
            form_class=FlowForm, can_create=True, can_delete=True,
        ),
        Resource(
            "prompts", "Plantillas de prompt", PromptTemplate,
            columns=[("Título", "title"), ("Momento", "momento_tipo"), ("Curso", lambda o: o.course or "Global"), ("Flujo", "n8n_flow"), ("Orden", "order"), ("Activa", _bool("is_active"))],
            search=("title", "description"),
            fields=["course", "momento_tipo", "title", "description", "n8n_flow", "order", "is_active"],
            select_related=("course", "n8n_flow"), can_create=True, can_delete=True,
        ),
        Resource(
            "students", "Estudiantes", Student,
            columns=[("Nombre", "name"), ("Email", "email"), ("Login", "login_id"), ("Canvas ID", "canvas_user_id"), ("Alta", lambda o: o.created_at.strftime("%Y-%m-%d"))],
            search=("name", "email", "login_id", "canvas_user_id"),
            ordering=("name",),
        ),
        Resource(
            "ledger", "Ledger de tokens", TokenUsageLedger,
            columns=[("Fecha", lambda o: o.created_at.strftime("%Y-%m-%d %H:%M")), ("Matrícula", "enrollment"), ("Tokens", "tokens_total"), ("Nota", "note")],
            search=("enrollment__student__name", "enrollment__student__email", "note"),
            select_related=("enrollment__student", "enrollment__course"), ordering=("-created_at",),
        ),
        Resource(
            "launch_logs", "Logs de lanzamiento LTI", LtiLaunchLog,
            columns=[("Fecha", lambda o: o.created_at.strftime("%Y-%m-%d %H:%M:%S")), ("Válido", _bool("validated")), ("Issuer", "issuer"), ("Sub", "sub"), ("IP", "ip_address"), ("Error", lambda o: (o.error or "")[:80])],
            search=("sub", "issuer", "ip_address", "error"), ordering=("-created_at",),
        ),
        Resource(
            "audit", "Auditoría del portal", AuditLog,
            columns=[("Fecha", lambda o: o.created_at.strftime("%Y-%m-%d %H:%M:%S")), ("Usuario", "username"), ("Acción", "action"), ("Recurso", "resource"), ("Objeto", "object_repr"), ("Detalle", lambda o: o.detail[:100]), ("IP", "ip_address")],
            search=("username", "action", "resource", "object_repr", "detail"), ordering=("-created_at",),
        ),
    ]
}
