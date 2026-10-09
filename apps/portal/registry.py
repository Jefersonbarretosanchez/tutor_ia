"""
Recursos del portal gestionados por las vistas genéricas (listado + formulario).

Cada Resource enlaza un modelo existente con las columnas del listado, los
campos del formulario y la clave de permisos (ver permissions.CATALOG).
Las vistas con lógica propia (usuarios, roles, matrículas, conversaciones)
viven en views.py.
"""

from dataclasses import dataclass, field

from apps.chat.models import TokenUsageLedger
from apps.lti_tool.models import Course, CoursePageGate, DefaultPageGate, LtiLaunchLog, Student

from . import audit
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
    singular: str = ""  # nombre en singular para los títulos del formulario
    labels: dict = field(default_factory=dict)  # etiquetas en español del formulario


def _bool(attr):
    return lambda o: "Sí" if getattr(o, attr) else "No"


RESOURCES = {
    r.key: r
    for r in [
        Resource(
            "courses", "Cursos", Course, singular="curso",
            columns=[
                ("Título", lambda o: o.title or o.context_id),
                ("ID de contexto", "context_id"),
                ("Límite tokens", lambda o: o.effective_token_limit),
                ("Activo", _bool("is_active")),
                ("AGS", lambda o: "Sí" if o.ags_lineitems_url else "No"),
            ],
            search=("title", "context_id", "canvas_course_id"),
            fields=["title", "token_limit", "show_unit_token_count", "show_course_token_usage", "is_active"],
            labels={"title": "Título", "token_limit": "Límite de tokens por estudiante",
                    "show_unit_token_count": "Mostrar al estudiante los tokens por unidad",
                    "show_course_token_usage": "Mostrar al estudiante el consumo total del curso", "is_active": "Curso activo"},
        ),
        Resource(
            "gates", "Páginas bloqueadas por curso", CoursePageGate, singular="página bloqueada",
            columns=[
                ("Curso", "course"), ("Momento", "momento"), ("Página Canvas", "canvas_page_url"),
                ("Texto del botón", "label"), ("Orden", "order"),
                ("Bloqueada", lambda o: o.locked_at.strftime("%Y-%m-%d %H:%M") if o.locked_at else "No"),
            ],
            search=("canvas_page_url", "momento", "label", "course__title"),
            fields=["course", "momento", "canvas_page_url", "label", "icon", "order"],
            labels={"course": "Curso", "momento": "Momento", "canvas_page_url": "Página de Canvas (slug)", "label": "Texto del botón", "icon": "Ícono (Font Awesome)", "order": "Orden"},
            select_related=("course",), can_create=True, can_delete=True,
            extra_actions=(("lock", "portal:gate_lock", "Bloquear en Canvas"),),
        ),
        Resource(
            "default_gates", "Bloqueos por defecto", DefaultPageGate, singular="bloqueo por defecto",
            columns=[("Momento", "momento"), ("Página Canvas", "canvas_page_url"), ("Texto del botón", "label"), ("Orden", "order")],
            search=("canvas_page_url", "momento", "label"),
            fields=["momento", "canvas_page_url", "label", "icon", "order"],
            labels={"course": "Curso", "momento": "Momento", "canvas_page_url": "Página de Canvas (slug)", "label": "Texto del botón", "icon": "Ícono (Font Awesome)", "order": "Orden"},
            can_create=True, can_delete=True,
        ),
        Resource(
            "students", "Estudiantes", Student,
            columns=[("Nombre", "name"), ("Correo", "email"), ("Usuario Canvas", "login_id"), ("Canvas ID", "canvas_user_id"), ("Alta", lambda o: o.created_at.strftime("%Y-%m-%d"))],
            search=("name", "email", "login_id", "canvas_user_id"),
            ordering=("name",),
        ),
        Resource(
            "ledger", "Registro de tokens", TokenUsageLedger,
            columns=[("Fecha", lambda o: o.created_at.strftime("%Y-%m-%d %H:%M")), ("Matrícula", "enrollment"), ("Tokens", "tokens_total"), ("Nota", "note")],
            search=("enrollment__student__name", "enrollment__student__email", "note"),
            select_related=("enrollment__student", "enrollment__course"), ordering=("-created_at",),
        ),
        Resource(
            "launch_logs", "Registros de lanzamiento LTI", LtiLaunchLog,
            columns=[("Fecha", lambda o: o.created_at.strftime("%Y-%m-%d %H:%M:%S")), ("Válido", _bool("validated")), ("Emisor", "issuer"), ("Identificador (sub)", "sub"), ("IP", "ip_address"), ("Error", lambda o: (o.error or "")[:80])],
            search=("sub", "issuer", "ip_address", "error"), ordering=("-created_at",),
        ),
        Resource(
            "audit", "Auditoría del portal", AuditLog,
            columns=[("Fecha", lambda o: o.created_at.strftime("%Y-%m-%d %H:%M:%S")), ("Usuario", "username"), ("Acción", audit.action_label), ("Sección", audit.resource_label), ("Objeto", "object_repr"), ("Detalle", lambda o: o.detail[:100]), ("IP", "ip_address")],
            search=("username", "action", "object_repr", "detail"), ordering=("-created_at",),
        ),
    ]
}
