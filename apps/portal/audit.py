from .models import AuditLog
from .permissions import CATALOG

ACTION_LABELS = {
    "login": "Inicio de sesión",
    "logout": "Cierre de sesión",
    "login_failed": "Intento de ingreso fallido",
    "password_change": "Cambio de contraseña",
    "create": "Creó",
    "edit": "Editó",
    "delete": "Eliminó",
    "edit_matrix": "Editó permisos del rol",
    "lock_page": "Bloqueó una página",
    "reactivate_chat": "Reactivó el chat",
    "credit_tokens": "Acreditó tokens",
    "reset_chat": "Reinició el chat",
    "view_conversation": "Abrió una conversación",
}


def action_label(entry):
    return ACTION_LABELS.get(entry.action, entry.action)


def resource_label(entry):
    if entry.resource == "auth":
        return "Autenticación"
    return CATALOG[entry.resource][0] if entry.resource in CATALOG else entry.resource


def client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")


def log(request, action, resource="", obj="", detail=""):
    user = request.user if request.user.is_authenticated else None
    AuditLog.objects.create(
        user=user,
        username=user.get_username() if user else request.POST.get("username", "")[:150],
        action=action,
        resource=resource,
        object_repr=str(obj)[:255],
        detail=detail,
        ip_address=client_ip(request),
    )
