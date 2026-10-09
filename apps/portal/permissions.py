"""
Catálogo de recursos/acciones del portal y chequeo de permisos.

La matriz rol × (recurso, acción) se guarda en BD (RolePermission) y se edita
desde el portal; este catálogo solo define QUÉ se puede permitir. El rol
`super_admin` (y cualquier is_superuser) tiene todo, siempre.
"""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import Role, RolePermission

VIEW, CREATE, EDIT, DELETE = "view", "create", "edit", "delete"
_CRUD = {VIEW: "Ver", CREATE: "Crear", EDIT: "Editar", DELETE: "Eliminar"}

# resource -> (etiqueta, {acción: etiqueta})
CATALOG = {
    "users": ("Usuarios del portal", _CRUD),
    "roles": ("Roles y permisos", _CRUD),
    "courses": ("Cursos", {VIEW: "Ver", EDIT: "Editar (límites, banderas)"}),
    "gates": ("Páginas gate por curso", {**_CRUD, "lock": "Bloquear en Canvas"}),
    "default_gates": ("Gates por defecto", _CRUD),
    "enrollments": ("Matrículas", {VIEW: "Ver", "reactivate": "Reactivar chat"}),
    "ledger": ("Ledger de tokens", {VIEW: "Ver", "adjust": "Ajustar créditos"}),
    "students": ("Estudiantes", {VIEW: "Ver"}),
    "flows": ("Flujos n8n", _CRUD),
    "prompts": ("Plantillas de prompt", _CRUD),
    "conversations": ("Conversaciones", {VIEW: "Ver contenido"}),
    "launch_logs": ("Logs de lanzamiento LTI", {VIEW: "Ver"}),
    "audit": ("Auditoría del portal", {VIEW: "Ver"}),
}

ALL_PERMISSIONS = {(r, a) for r, (_, acts) in CATALOG.items() for a in acts}

_VIEW_ONLY = {(r, VIEW) for r in CATALOG}

# Matriz por defecto (se siembra con `seed_portal`; luego se edita desde el portal).
DEFAULT_ROLES = {
    "super_admin": ("Super admin", "Acceso total, gestiona usuarios y roles.", ALL_PERMISSIONS),
    "admin_plataforma": (
        "Admin plataforma",
        "Opera toda la plataforma; solo ve usuarios y roles.",
        {p for p in ALL_PERMISSIONS if p[0] not in ("users", "roles")} | {("users", VIEW), ("roles", VIEW)},
    ),
    "coordinador": (
        "Coordinador de curso",
        "Ve todos los cursos; edita cursos, gates, matrículas y prompts.",
        {
            ("courses", VIEW), ("courses", EDIT),
            ("gates", VIEW), ("gates", CREATE), ("gates", EDIT), ("gates", "lock"),
            ("enrollments", VIEW), ("enrollments", "reactivate"),
            ("ledger", VIEW), ("students", VIEW),
            ("prompts", VIEW), ("prompts", CREATE), ("prompts", EDIT),
            ("conversations", VIEW), ("launch_logs", VIEW),
        },
    ),
    "soporte": (
        "Soporte",
        "Consulta y reactiva el chat de estudiantes.",
        {
            ("courses", VIEW), ("gates", VIEW), ("default_gates", VIEW),
            ("enrollments", VIEW), ("enrollments", "reactivate"),
            ("ledger", VIEW), ("students", VIEW), ("launch_logs", VIEW),
        },
    ),
    "auditor": (
        "Auditor",
        "Solo lectura de todo (incluye conversaciones y auditoría).",
        _VIEW_ONLY,
    ),
}


def _permission_set(user):
    cached = getattr(user, "_portal_perms", None)
    if cached is not None:
        return cached
    if not user.is_authenticated or not user.is_active:
        perms = frozenset()
    elif user.is_superuser:
        perms = frozenset(ALL_PERMISSIONS)
    else:
        ur = getattr(user, "portal_role", None)
        if ur is None:
            perms = frozenset()
        elif ur.role.code == Role.SUPER_ADMIN:
            perms = frozenset(ALL_PERMISSIONS)
        else:
            perms = frozenset(RolePermission.objects.filter(role=ur.role).values_list("resource", "action"))
    user._portal_perms = perms
    return perms


def can(user, resource, action=VIEW):
    return (resource, action) in _permission_set(user)


def is_portal_user(user):
    return user.is_authenticated and user.is_active and (user.is_superuser or hasattr(user, "portal_role"))


def require(resource, action=VIEW):
    """Decorador de vistas: login + permiso (recurso, acción). Se valida siempre en servidor."""

    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not is_portal_user(request.user):
                return redirect_to_login(request.get_full_path(), "portal:login")
            if not can(request.user, resource, action):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return deco
