from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import AuditLog, Role, RolePermission, UserRole

User = get_user_model()
PWD = "Clave-Segura-123"


def make_user(username, role_code, must_change=False):
    u = User.objects.create_user(username, f"{username}@x.com", PWD)
    UserRole.objects.create(user=u, role=Role.objects.get(code=role_code), must_change_password=must_change)
    return u


class PortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_portal", verbosity=0)
        cls.sa = make_user("boss", "super_admin")
        cls.coord = make_user("coord", "coordinador")
        cls.soporte = make_user("sop", "soporte")

    def setUp(self):
        cache.clear()

    def login(self, username):
        self.client.logout()
        return self.client.post(reverse("portal:login"), {"username": username, "password": PWD})

    def test_password_hashed_with_argon2(self):
        self.assertTrue(User.objects.get(username="boss").password.startswith("argon2$"))

    def test_anonymous_redirected_to_login(self):
        r = self.client.get(reverse("portal:dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/portal/login/", r["Location"])

    def test_login_ok_and_user_without_role_rejected(self):
        self.assertEqual(self.login("boss").status_code, 302)
        User.objects.create_user("norole", password=PWD)
        r = self.login("norole")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "no tiene acceso")

    def test_login_lockout_after_failures(self):
        for _ in range(5):
            self.client.post(reverse("portal:login"), {"username": "boss", "password": "mala"})
        r = self.login("boss")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Demasiados intentos")

    def test_permissions_enforced_server_side(self):
        self.login("sop")
        self.assertEqual(self.client.get(reverse("portal:user_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("portal:resource_list", args=["flows"])).status_code, 403)
        self.assertEqual(self.client.get(reverse("portal:enrollment_list")).status_code, 200)
        # soporte puede ver cursos pero no editarlos
        self.assertEqual(self.client.get(reverse("portal:resource_create", args=["gates"])).status_code, 403)

    def test_coordinator_sees_all_courses_but_not_users(self):
        self.login("coord")
        self.assertEqual(self.client.get(reverse("portal:resource_list", args=["courses"])).status_code, 200)
        self.assertEqual(self.client.get(reverse("portal:role_list")).status_code, 403)

    def test_matrix_edit_changes_access_and_is_audited(self):
        role = Role.objects.get(code="soporte")
        self.login("boss")
        self.client.post(reverse("portal:role_matrix", args=[role.pk]), {"perm": ["flows:view", "bogus:view"]})
        perms = set(RolePermission.objects.filter(role=role).values_list("resource", "action"))
        self.assertEqual(perms, {("flows", "view")})
        self.assertTrue(AuditLog.objects.filter(action="edit_matrix").exists())
        self.login("sop")
        self.assertEqual(self.client.get(reverse("portal:resource_list", args=["flows"])).status_code, 200)

    def test_super_admin_matrix_is_locked(self):
        role = Role.objects.get(code="super_admin")
        self.login("boss")
        self.assertEqual(self.client.post(reverse("portal:role_matrix", args=[role.pk]), {"perm": []}).status_code, 403)

    def test_cannot_demote_last_super_admin(self):
        self.login("boss")
        r = self.client.post(reverse("portal:user_edit", args=[self.sa.pk]), {
            "username": "boss", "email": "boss@x.com", "is_active": "on", "role": Role.objects.get(code="auditor").pk,
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "al menos un super admin")

    def test_create_user_forces_password_change(self):
        self.login("boss")
        r = self.client.post(reverse("portal:user_create"), {
            "username": "nuevo", "email": "n@x.com", "is_active": "on",
            "role": Role.objects.get(code="auditor").pk, "password": "Otra-Clave-Larga-9",
        })
        self.assertEqual(r.status_code, 302)
        self.client.logout()
        self.client.post(reverse("portal:login"), {"username": "nuevo", "password": "Otra-Clave-Larga-9"})
        r = self.client.get(reverse("portal:dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/portal/password/", r["Location"])

    def test_weak_password_rejected(self):
        self.login("boss")
        r = self.client.post(reverse("portal:user_create"), {
            "username": "debil", "is_active": "on", "role": Role.objects.get(code="auditor").pk, "password": "123",
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="debil").exists())

    def test_logout_requires_post(self):
        self.login("boss")
        self.assertEqual(self.client.get(reverse("portal:logout")).status_code, 405)

    def test_every_page_renders_for_super_admin(self):
        from .registry import RESOURCES

        self.login("boss")
        urls = [reverse("portal:dashboard"), reverse("portal:enrollment_list"), reverse("portal:conversation_list"),
                reverse("portal:user_list"), reverse("portal:user_create"), reverse("portal:user_edit", args=[self.sa.pk]),
                reverse("portal:role_list"), reverse("portal:role_create"), reverse("portal:password_change")]
        urls += [reverse("portal:role_matrix", args=[r.pk]) for r in Role.objects.all()]
        for key, res in RESOURCES.items():
            urls.append(reverse("portal:resource_list", args=[key]))
            if res.can_create:
                urls.append(reverse("portal:resource_create", args=[key]))
        for url in urls:
            for extra in ("", "?q=x"):
                r = self.client.get(url + (extra if "r/" in url or "users" in url else ""), HTTP_HX_REQUEST="true" if extra else "")
                self.assertEqual(r.status_code, 200, url)

    def _enrollment(self, limit=100):
        from django.utils import timezone
        from pylti1p3.contrib.django.lti1p3_tool_config.models import LtiTool

        from apps.chat.models import TokenUsageLedger
        from apps.lti_tool.models import Course, CourseEnrollment, Student

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from pylti1p3.contrib.django.lti1p3_tool_config.models import LtiToolKey

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        pub = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        tool = LtiTool.objects.create(
            title="t", issuer="https://i", client_id="c", auth_login_url="https://a", auth_token_url="https://b",
            auth_audience="", key_set_url="https://k", tool_key=LtiToolKey.objects.create(name="k", private_key=priv, public_key=pub),
        )
        course = Course.objects.create(lti_tool=tool, deployment_id="d", context_id="c1", title="C1", token_limit=limit)
        student = Student.objects.create(lti_tool=tool, deployment_id="d", sub="s1", name="Ana")
        e = CourseEnrollment.objects.create(student=student, course=course, chat_enabled=False, limit_reached_at=timezone.now())
        TokenUsageLedger.objects.create(enrollment=e, tokens_total=limit)
        return e

    def test_reactivate_and_credit_actions(self):
        from apps.chat.models import TokenUsageLedger

        from django.utils import timezone

        e = self._enrollment()
        # soporte: puede reactivar pero NO acreditar
        self.login("sop")
        self.assertEqual(self.client.post(reverse("portal:enrollment_credit", args=[e.pk]), {"tokens": 10, "note": "x"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("portal:enrollment_reactivate", args=[e.pk]), HTTP_HX_REQUEST="true").status_code, 200)
        e.refresh_from_db()
        self.assertTrue(e.chat_enabled)
        # admin: acredita y queda auditado en el ledger
        e.chat_enabled, e.limit_reached_at = False, timezone.now()
        e.save()
        self.login("boss")
        r = self.client.post(reverse("portal:enrollment_credit", args=[e.pk]), {"tokens": 30, "note": "compensación"}, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        e.refresh_from_db()
        self.assertTrue(e.chat_enabled)
        self.assertEqual(TokenUsageLedger.total_for(e), 70)
        self.assertTrue(AuditLog.objects.filter(action="credit_tokens").exists())
        self.assertEqual(self.client.get(reverse("portal:enrollment_list")).status_code, 200)
