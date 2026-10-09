from django.conf import settings
from django.db import models


class Role(models.Model):
    """Rol del portal. Sus permisos viven en RolePermission (matriz recurso × acción)."""

    SUPER_ADMIN = "super_admin"

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    is_system = models.BooleanField(
        default=False,
        help_text="Los roles de sistema no se pueden eliminar; 'super_admin' además tiene todos los permisos siempre.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    resource = models.CharField(max_length=50)
    action = models.CharField(max_length=50)

    class Meta:
        unique_together = [("role", "resource", "action")]

    def __str__(self):
        return f"{self.role} · {self.resource}.{self.action}"


class UserRole(models.Model):
    """Un usuario del portal tiene exactamente un rol."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="portal_role")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="user_roles")
    must_change_password = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user} → {self.role}"


class AuditLog(models.Model):
    """Quién cambió qué y cuándo en el portal (append-only)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=50)
    resource = models.CharField(max_length=50, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    detail = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
