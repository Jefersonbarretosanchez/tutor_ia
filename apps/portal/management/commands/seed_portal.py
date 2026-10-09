from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.portal.models import Role, RolePermission, UserRole
from apps.portal.permissions import DEFAULT_ROLES

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Siembra los roles por defecto del portal. Con --reset-permissions también restablece la "
        "matriz de los roles existentes (por defecto solo crea los que faltan). "
        "Con --superadmin USUARIO asigna ese usuario (existente) como super admin."
    )

    def add_arguments(self, parser):
        parser.add_argument("--reset-permissions", action="store_true")
        parser.add_argument("--superadmin", metavar="USUARIO")

    @transaction.atomic
    def handle(self, *args, **opts):
        for code, (name, desc, perms) in DEFAULT_ROLES.items():
            role, created = Role.objects.get_or_create(code=code, defaults={"name": name, "description": desc, "is_system": True})
            if created or opts["reset_permissions"]:
                RolePermission.objects.filter(role=role).delete()
                RolePermission.objects.bulk_create(RolePermission(role=role, resource=r, action=a) for r, a in sorted(perms))
            self.stdout.write(f"{'creado' if created else 'existente'}: {code}")

        if opts["superadmin"]:
            try:
                user = User.objects.get(username=opts["superadmin"])
            except User.DoesNotExist:
                raise CommandError(f"El usuario '{opts['superadmin']}' no existe (créalo con createsuperuser).")
            UserRole.objects.update_or_create(
                user=user, defaults={"role": Role.objects.get(code=Role.SUPER_ADMIN), "must_change_password": False}
            )
            self.stdout.write(self.style.SUCCESS(f"{user.username} es ahora super admin del portal."))
