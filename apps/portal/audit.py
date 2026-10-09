from .models import AuditLog


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
