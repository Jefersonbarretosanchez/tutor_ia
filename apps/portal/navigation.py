"""
Estructura única de navegación del portal: alimenta el sidebar, la paleta
de comandos (Ctrl+K) y las migas de pan. Cada ítem solo aparece si el rol
del usuario tiene el permiso de ver ese recurso.
"""

from django.urls import reverse

from apps.lti_tool.models import CourseEnrollment

from .permissions import can

# (grupo, [(clave, etiqueta, icono, url_name, url_args, permiso)])
NAV = [
    (None, [("home", "Inicio", "home", "portal:dashboard", (), None)]),
    ("Operación", [
        ("enrollments", "Matrículas y tokens", "users", "portal:enrollment_list", (), "enrollments"),
        ("conversations", "Conversaciones", "chat", "portal:conversation_list", (), "conversations"),
        ("courses", "Cursos", "layers", "portal:resource_list", ("courses",), "courses"),
        ("students", "Estudiantes", "user", "portal:resource_list", ("students",), "students"),
        ("ledger", "Registro de tokens", "coins", "portal:resource_list", ("ledger",), "ledger"),
    ]),
    ("Configuración", [
        ("gates", "Páginas bloqueadas", "lock", "portal:resource_list", ("gates",), "gates"),
        ("default_gates", "Bloqueos por defecto", "lock-open", "portal:resource_list", ("default_gates",), "default_gates"),
    ]),
    ("Monitoreo", [
        ("launch_logs", "Lanzamientos LTI", "pulse", "portal:resource_list", ("launch_logs",), "launch_logs"),
        ("audit", "Auditoría", "shield", "portal:resource_list", ("audit",), "audit"),
    ]),
    ("Accesos", [
        ("users", "Usuarios", "key", "portal:user_list", (), "users"),
        ("roles", "Roles y permisos", "grid", "portal:role_list", (), "roles"),
    ]),
]


def nav_for(user, current_key=None):
    groups = []
    for label, items in NAV:
        visible = [
            {"key": k, "label": lbl, "icon": icon, "url": reverse(url, args=args), "active": k == current_key}
            for k, lbl, icon, url, args, perm in items
            if perm is None or can(user, perm)
        ]
        if visible:
            groups.append({"label": label, "items": visible})
    return groups


def _current_key(request):
    match = request.resolver_match
    if not match or match.app_name != "portal":
        return None
    name = match.url_name
    if name == "dashboard":
        return "home"
    if name.startswith("resource_"):
        return match.kwargs.get("key")
    for prefix, key in (("enrollment", "enrollments"), ("conversation", "conversations"), ("user_", "users"), ("role_", "roles"), ("gate_", "gates")):
        if name.startswith(prefix):
            return key
    return None


def portal_context(request):
    """Context processor: navegación filtrada por permisos + contador de chats bloqueados."""
    user = request.user
    if not user.is_authenticated or not request.path.startswith("/portal/") or getattr(request, "resolver_match", None) is None:
        return {}
    groups = nav_for(user, _current_key(request))
    if can(user, "enrollments"):
        blocked = CourseEnrollment.objects.filter(chat_enabled=False, is_instructor=False).count()
        for g in groups:
            for item in g["items"]:
                if item["key"] == "enrollments":
                    item["badge"] = blocked or None
    return {"nav_groups": groups, "palette_items": [i for g in groups for i in g["items"]]}
