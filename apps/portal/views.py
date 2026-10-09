from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError, Q, Sum
from django.db.models.functions import TruncDate
from django.forms import modelform_factory
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.chat.models import ClaraMessage, ClaraMoment, TokenUsageLedger
from apps.chat.services import canvas_pages
from apps.lti_tool.models import Course, CourseEnrollment, CoursePageGate, LtiLaunchLog, Student

from . import audit
from .forms import CreditForm, PasswordChangeForm, PortalAuthenticationForm, ResetChatForm, RoleForm, UserForm
from .models import AuditLog, Role, RolePermission, UserRole
from .permissions import ALL_PERMISSIONS, CATALOG, CREATE, DELETE, EDIT, VIEW, can, is_portal_user, require
from .registry import RESOURCES

User = get_user_model()

PAGE_SIZE = 25
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 15 * 60


# --------------------------------------------------------------------------
# Utilidades: paginación, HTMX y paneles (modal o página completa)
# --------------------------------------------------------------------------


def _page(request, qs):
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    page.qs = params.urlencode() + "&" if params else ""
    return page


def _htmx(request):
    return request.headers.get("HX-Request") == "true"


def _panel(request, *, title, body, action="", form=None, submit="Guardar", crumbs=(), wide=False, actions=(), ctx=None, danger=False):
    """
    Un mismo contenido sirve como modal (si la petición viene de HTMX) o como página
    completa (acceso directo por URL). `submit=None` => panel de solo lectura/sin envío.
    """
    modal = _htmx(request)
    context = {
        "title": title, "body": body, "action": action or request.get_full_path(), "form": form, "submit": submit,
        "crumbs": crumbs, "wide": wide, "actions": actions, "modal": modal, "danger": danger,
        "back": crumbs[-2][1] if len(crumbs) > 1 else None, **(ctx or {}),
    }
    return render(request, "portal/_panel.html" if modal else "portal/panel_page.html", context)


def _done(request, url):
    """Éxito de un panel: desde modal se recarga la página destino (con su aviso); si no, redirección normal."""
    if _htmx(request):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return redirect(url)


def _back(request, fallback):
    ref = request.META.get("HTTP_REFERER", "")
    return ref if ref and url_has_allowed_host_and_scheme(ref, allowed_hosts={request.get_host()}) else fallback


def _is_last_super_admin(user):
    """True si `user` es el único super admin activo (no se puede quitar/desactivar)."""
    def is_super(u):
        return u.is_superuser or (hasattr(u, "portal_role") and u.portal_role.role.code == Role.SUPER_ADMIN)

    if not is_super(user):
        return False
    others = [u for u in User.objects.filter(is_active=True).exclude(pk=user.pk).select_related("portal_role__role") if is_super(u)]
    return not others


def _need_login(request):
    return redirect_to_login(request.get_full_path(), "portal:login")


# --------------------------------------------------------------------------
# Autenticación
# --------------------------------------------------------------------------


def login_view(request):
    if is_portal_user(request.user):
        return redirect("portal:dashboard")

    form = PortalAuthenticationForm(request, data=(request.POST if request.method == "POST" else None))
    if request.method == "POST":
        key = f"portal-login:{audit.client_ip(request)}:{request.POST.get('username', '').lower()[:150]}"
        if cache.get(key, 0) >= LOGIN_MAX_FAILURES:
            form.add_error(None, "Demasiados intentos fallidos. Espera 15 minutos e inténtalo de nuevo.")
        elif form.is_valid():
            cache.delete(key)
            auth_login(request, form.get_user())
            audit.log(request, "login", "auth", request.user)
            nxt = request.POST.get("next") or request.GET.get("next") or ""
            if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
                return redirect(nxt)
            return redirect("portal:dashboard")
        else:
            cache.set(key, cache.get(key, 0) + 1, LOGIN_LOCK_SECONDS)
            audit.log(request, "login_failed", "auth", request.POST.get("username", ""))
    return render(request, "portal/login.html", {"form": form, "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        audit.log(request, "logout", "auth", request.user)
    auth_logout(request)
    return redirect("portal:login")


def password_change(request):
    if not is_portal_user(request.user):
        return redirect("portal:login")
    form = PasswordChangeForm(request.user, (request.POST if request.method == "POST" else None))
    forced = hasattr(request.user, "portal_role") and request.user.portal_role.must_change_password
    if request.method == "POST" and form.is_valid():
        request.user.set_password(form.cleaned_data["new"])
        request.user.save()
        UserRole.objects.filter(user=request.user).update(must_change_password=False)
        update_session_auth_hash(request, request.user)
        audit.log(request, "password_change", "auth", request.user)
        messages.success(request, "Contraseña actualizada.")
        return _done(request, reverse("portal:dashboard") if forced else _back(request, reverse("portal:dashboard")))
    return _panel(
        request, title="Cambiar contraseña", body="portal/_body_password.html", form=form, submit="Guardar contraseña",
        crumbs=[("Inicio", reverse("portal:dashboard")), ("Cambiar contraseña", None)], ctx={"forced": forced},
    )


# --------------------------------------------------------------------------
# Inicio y búsqueda global
# --------------------------------------------------------------------------


def dashboard(request):
    if not is_portal_user(request.user):
        return _need_login(request)

    students = CourseEnrollment.objects.filter(is_instructor=False)
    blocked = students.filter(chat_enabled=False).count()
    near_limit = sum(
        1
        for e in _enrollment_qs().filter(is_instructor=False, chat_enabled=True)
        if (e.used or 0) >= e.course.effective_token_limit * settings.TOKEN_WARNING_THRESHOLD_PCT / 100
    )
    since = timezone.now() - timedelta(days=13)
    per_day = dict(
        TokenUsageLedger.objects.filter(created_at__gte=since, tokens_total__gt=0)
        .annotate(day=TruncDate("created_at"))
        .values_list("day")
        .annotate(total=Sum("tokens_total"))
    )
    days = [(since + timedelta(days=i)).date() for i in range(14)]
    peak = max([per_day.get(d, 0) for d in days] + [1])
    chart = [{"day": d, "total": per_day.get(d, 0), "pct": round(per_day.get(d, 0) * 100 / peak), "weekend": d.weekday() >= 5} for d in days]

    ctx = {
        "courses": Course.objects.filter(is_active=True).count(),
        "students": students.count(),
        "blocked": blocked,
        "near_limit": near_limit,
        "tokens": TokenUsageLedger.objects.aggregate(t=Sum("tokens_total"))["t"] or 0,
        "chart": chart,
        "today": timezone.localdate(),
        "can_enrollments": can(request.user, "enrollments", VIEW),
        "can_logs": can(request.user, "launch_logs", VIEW),
        "can_audit": can(request.user, "audit", VIEW),
    }
    if ctx["can_logs"]:
        ctx["failed_today"] = LtiLaunchLog.objects.filter(validated=False, created_at__date=ctx["today"]).count()
        ctx["last_failed"] = LtiLaunchLog.objects.filter(validated=False).order_by("-created_at").first()
    if ctx["can_audit"]:
        recent = AuditLog.objects.exclude(action__in=["login", "logout", "login_failed", "view_conversation"])[:6]
        ctx["activity"] = [{"entry": a, "action": audit.action_label(a), "section": audit.resource_label(a)} for a in recent]
    return render(request, "portal/dashboard.html", ctx)


@require("courses", VIEW)
def search(request):
    """Resultados de la paleta de comandos (HTMX): estudiantes y cursos que coinciden."""
    q = request.GET.get("q", "").strip()
    results = []
    if len(q) >= 2:
        if can(request.user, "enrollments", VIEW):
            for st in Student.objects.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(login_id__icontains=q))[:5]:
                results.append({"label": st.name or st.login_id, "hint": st.email, "kind": "Estudiante",
                                "url": f"{reverse('portal:enrollment_list')}?q={quote(st.email or st.name or st.login_id)}"})
        for c in Course.objects.filter(Q(title__icontains=q) | Q(context_id__icontains=q))[:5]:
            results.append({"label": c.title or c.context_id, "hint": c.context_id, "kind": "Curso",
                            "url": reverse("portal:resource_list", args=["courses"]) + f"?q={quote(c.context_id)}"})
    return render(request, "portal/_search_results.html", {"results": results, "q": q})


# --------------------------------------------------------------------------
# Recursos genéricos (cursos, páginas bloqueadas, y listados de solo lectura)
# --------------------------------------------------------------------------


def _resource(key):
    try:
        return RESOURCES[key]
    except KeyError:
        raise Http404


def _cells(res, obj):
    return [(header, col(obj) if callable(col) else getattr(obj, col)) for header, col in res.columns]


def resource_list(request, key):
    res = _resource(key)
    if not is_portal_user(request.user):
        return _need_login(request)
    if not can(request.user, key, VIEW):
        raise PermissionDenied

    qs = res.model.objects.all()
    if res.select_related:
        qs = qs.select_related(*res.select_related)
    if res.ordering:
        qs = qs.order_by(*res.ordering)
    q = request.GET.get("q", "").strip()
    if q and res.search:
        cond = Q()
        for f in res.search:
            cond |= Q(**{f"{f}__icontains": q})
        qs = qs.filter(cond)

    page = _page(request, qs)
    rows = [{"obj": o, "cells": _cells(res, o)} for o in page]
    ctx = {
        "res": res, "page": page, "rows": rows, "q": q,
        "can_edit": bool(res.fields) and can(request.user, key, EDIT),
        "can_create": res.can_create and can(request.user, key, CREATE),
        "can_delete": res.can_delete and can(request.user, key, DELETE),
        "extra_actions": [a for a in res.extra_actions if can(request.user, key, a[0])],
    }
    return render(request, "portal/_table.html" if _htmx(request) else "portal/resource_list.html", ctx)


def resource_form(request, key, pk=None):
    res = _resource(key)
    action = EDIT if pk else CREATE
    if not is_portal_user(request.user):
        return _need_login(request)
    if not res.fields or not can(request.user, key, action) or (not pk and not res.can_create):
        raise PermissionDenied

    obj = get_object_or_404(res.model, pk=pk) if pk else None
    form_cls = res.form_class or modelform_factory(res.model, fields=res.fields, labels=res.labels)
    form = form_cls((request.POST if request.method == "POST" else None), instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        changed = ", ".join(f for f in form.changed_data if f != "shared_secret") or "—"
        audit.log(request, "create" if not pk else "edit", key, saved, f"campos: {changed}")
        messages.success(request, "Guardado correctamente.")
        return _done(request, reverse("portal:resource_list", kwargs={"key": key}))
    return _panel(
        request, title=f"{'Editar' if obj else 'Nuevo'} · {res.singular}", body="portal/_body_fields.html", form=form,
        crumbs=[("Inicio", reverse("portal:dashboard")), (res.label, reverse("portal:resource_list", kwargs={"key": key})), ("Editar" if obj else "Nuevo", None)],
    )


@require_POST
def resource_delete(request, key, pk):
    res = _resource(key)
    if not is_portal_user(request.user) or not res.can_delete or not can(request.user, key, DELETE):
        raise PermissionDenied
    obj = get_object_or_404(res.model, pk=pk)
    label = str(obj)
    try:
        obj.delete()
    except ProtectedError:
        messages.error(request, "No se puede eliminar: hay registros que dependen de este.")
    else:
        audit.log(request, "delete", key, label)
        messages.success(request, "Eliminado.")
    return redirect("portal:resource_list", key=key)


@require("gates", "lock")
@require_POST
def gate_lock(request, pk):
    gate = get_object_or_404(CoursePageGate.objects.select_related("course"), pk=pk)
    ok = canvas_pages.lock_page(gate)
    audit.log(request, "lock_page", "gates", gate, "ok" if ok else "falló")
    (messages.success if ok else messages.error)(
        request, "Página bloqueada en Canvas." if ok else "No se pudo bloquear la página (revisa canvas_course_id y token)."
    )
    return redirect("portal:resource_list", key="gates")


# --------------------------------------------------------------------------
# Matrículas (reactivar chat, créditos, reinicio)
# --------------------------------------------------------------------------


def _enrollment_row(e):
    used = e.used or 0
    limit = e.course.effective_token_limit
    return {"e": e, "used": used, "limit": limit, "pct": min(100, round(used * 100 / limit)) if limit else 0}


def _enrollment_qs():
    return CourseEnrollment.objects.select_related("student", "course").annotate(used=Sum("token_ledger__tokens_total"))


def _row_perms(user):
    return {
        "can_reactivate": can(user, "enrollments", "reactivate"),
        "can_adjust": can(user, "ledger", "adjust"),
        "can_reset": can(user, "conversations", "reset"),
    }


@require("enrollments", VIEW)
def enrollment_list(request):
    qs = _enrollment_qs().order_by("course__title", "student__name")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(student__name__icontains=q) | Q(student__email__icontains=q) | Q(student__login_id__icontains=q))
    course = request.GET.get("course", "")
    if course.isdigit():
        qs = qs.filter(course_id=course)
    status = request.GET.get("status", "")
    if status == "blocked":
        qs = qs.filter(chat_enabled=False)
    elif status == "active":
        qs = qs.filter(chat_enabled=True)
    elif status == "instructor":
        qs = qs.filter(is_instructor=True)

    page = _page(request, qs)
    base = CourseEnrollment.objects.all()
    ctx = {
        "page": page, "rows": [_enrollment_row(e) for e in page], "q": q, "status": status, "course": course,
        "chips": [("", "Todos", base.count()), ("blocked", "Bloqueados", base.filter(chat_enabled=False).count()),
                  ("active", "Activos", base.filter(chat_enabled=True).count()), ("instructor", "Instructores", base.filter(is_instructor=True).count())],
        "courses": Course.objects.all(),
        **_row_perms(request.user),
    }
    return render(request, "portal/_enrollment_table.html" if _htmx(request) else "portal/enrollment_list.html", ctx)


def _row_response(request, pk, flash):
    """Devuelve la fila actualizada; si venía de un modal, la inyecta en la tabla y cierra el modal."""
    e = get_object_or_404(_enrollment_qs(), pk=pk)
    response = render(request, "portal/_enrollment_row.html", {"r": _enrollment_row(e), "flash": flash, **_row_perms(request.user)})
    response["HX-Retarget"] = f"#enr-{pk}"
    response["HX-Reswap"] = "outerHTML"
    response["HX-Trigger"] = "close-modal"
    return response


def _reenable_if_below_limit(e):
    """Si el chat se bloqueó por límite y ya hay saldo, lo vuelve a habilitar."""
    if not e.chat_enabled and e.limit_reached_at and TokenUsageLedger.total_for(e) < e.course.effective_token_limit:
        e.chat_enabled = True
        e.limit_reached_at = None
        e.save(update_fields=["chat_enabled", "limit_reached_at"])


@require("enrollments", "reactivate")
@require_POST
def enrollment_reactivate(request, pk):
    e = get_object_or_404(CourseEnrollment, pk=pk)
    e.chat_enabled = True
    e.limit_reached_at = None
    e.save(update_fields=["chat_enabled", "limit_reached_at"])
    audit.log(request, "reactivate_chat", "enrollments", e)
    return _row_response(request, pk, "Chat reactivado.")


@require("ledger", "adjust")
def enrollment_credit(request, pk):
    e = get_object_or_404(CourseEnrollment.objects.select_related("student", "course"), pk=pk)
    form = CreditForm((request.POST if request.method == "POST" else None))
    if request.method == "POST" and form.is_valid():
        tokens = form.cleaned_data["tokens"]
        note = f"Crédito manual ({request.user.get_username()}): {form.cleaned_data['note']}"[:255]
        with transaction.atomic():
            TokenUsageLedger.objects.create(enrollment=e, tokens_total=-tokens, note=note)
            _reenable_if_below_limit(e)
        audit.log(request, "credit_tokens", "ledger", e, f"-{tokens} tokens · {form.cleaned_data['note']}")
        if _htmx(request):
            return _row_response(request, pk, f"{tokens:,} tokens acreditados.".replace(",", "."))
        messages.success(request, "Tokens acreditados.")
        return redirect("portal:enrollment_list")
    return _panel(
        request, title="Acreditar tokens", body="portal/_body_fields.html", form=form, submit="Acreditar",
        ctx={"lead": f"{e.student.name or e.student.login_id} · {e.course}"},
        crumbs=[("Inicio", reverse("portal:dashboard")), ("Matrículas y tokens", reverse("portal:enrollment_list")), ("Acreditar tokens", None)],
    )


# --------------------------------------------------------------------------
# Conversaciones (lectura + reinicio)
# --------------------------------------------------------------------------


def _reset_chat(request, enrollment, moments, refund):
    """
    Borra los momentos (y sus mensajes) para que el estudiante empiece de cero: en su próxima
    visita Django vuelve a pedir la apertura a Clara. Opcionalmente acredita en el registro los
    tokens que esas conversaciones consumieron. No revierte notas ni páginas ya desbloqueadas.
    """
    moments = list(moments)
    if not moments:
        return 0, 0
    credited = 0
    with transaction.atomic():
        if refund:
            credited = ClaraMessage.objects.filter(moment__in=moments, role=ClaraMessage.ROLE_ASSISTANT).aggregate(t=Sum("tokens_used"))["t"] or 0
            if credited:
                TokenUsageLedger.objects.create(
                    enrollment=enrollment, tokens_total=-credited,
                    note=f"Reinicio de chat ({request.user.get_username()}): tokens devueltos"[:255],
                )
        ClaraMoment.objects.filter(pk__in=[m.pk for m in moments]).delete()
        _reenable_if_below_limit(enrollment)
    audit.log(request, "reset_chat", "conversations", enrollment,
              f"{len(moments)} momento(s) borrado(s)" + (f" · {credited} tokens acreditados" if credited else ""))
    return len(moments), credited


def _reset_message(n, credited):
    if not n:
        return "No había conversaciones que reiniciar."
    return f"Chat reiniciado: {n} conversación(es) borrada(s)" + (f" y {credited:,} tokens acreditados.".replace(",", ".") if credited else ".")


def _reset_panel(request, enrollment, moments, title, lead, crumbs):
    form = ResetChatForm((request.POST if request.method == "POST" else None))
    if request.method == "POST" and form.is_valid():
        n, credited = _reset_chat(request, enrollment, moments, form.cleaned_data["refund"])
        messages.success(request, _reset_message(n, credited))
        return _done(request, _back(request, reverse("portal:enrollment_list")) if _htmx(request) else reverse("portal:conversation_list"))
    return _panel(
        request, title=title, body="portal/_body_fields.html", form=form, submit="Reiniciar chat", danger=True,
        ctx={"lead": lead, "warning": "Se borrarán los mensajes y el estudiante empezará de cero. Esta acción no se puede deshacer, "
                                       "ni revierte la nota enviada a Canvas ni las páginas ya desbloqueadas."},
        crumbs=crumbs,
    )


@require("conversations", "reset")
def conversation_reset(request, pk):
    moment = get_object_or_404(ClaraMoment.objects.select_related("enrollment__course", "enrollment__student"), pk=pk)
    student = moment.enrollment.student
    return _reset_panel(
        request, moment.enrollment, [moment], "Reiniciar conversación",
        f"{student.name or student.login_id} · {moment.get_momento_display()}",
        [("Inicio", reverse("portal:dashboard")), ("Conversaciones", reverse("portal:conversation_list")), ("Reiniciar", None)],
    )


@require("conversations", "reset")
def enrollment_reset_chat(request, pk):
    e = get_object_or_404(CourseEnrollment.objects.select_related("course", "student"), pk=pk)
    return _reset_panel(
        request, e, e.clara_moments.all(), "Reiniciar chat del estudiante",
        f"{e.student.name or e.student.login_id} · {e.course} · {e.clara_moments.count()} conversación(es)",
        [("Inicio", reverse("portal:dashboard")), ("Matrículas y tokens", reverse("portal:enrollment_list")), ("Reiniciar chat", None)],
    )


@require("conversations", VIEW)
def conversation_list(request):
    qs = ClaraMoment.objects.select_related("enrollment__student", "enrollment__course").order_by("-last_activity_at")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(enrollment__student__name__icontains=q) | Q(enrollment__student__email__icontains=q))
    momento = request.GET.get("momento", "")
    if momento:
        qs = qs.filter(momento=momento)
    ctx = {"page": _page(request, qs), "q": q, "momento": momento, "momentos": ClaraMoment.MOMENTO_CHOICES}
    return render(request, "portal/_conversation_table.html" if _htmx(request) else "portal/conversation_list.html", ctx)


@require("conversations", VIEW)
def conversation_detail(request, pk):
    moment = get_object_or_404(ClaraMoment.objects.select_related("enrollment__student", "enrollment__course"), pk=pk)
    audit.log(request, "view_conversation", "conversations", moment)
    student = moment.enrollment.student
    name = student.name or student.login_id
    actions = []
    if can(request.user, "conversations", "reset"):
        actions.append({"label": "Reiniciar esta conversación", "url": reverse("portal:conversation_reset", args=[pk]), "danger": True})
    return _panel(
        request, title=f"{name} · {moment.get_momento_display()}", body="portal/_body_conversation.html", submit=None, wide=True, actions=actions,
        ctx={"m": moment, "msgs": moment.messages.order_by("created_at"),
             "lead": f"{moment.enrollment.course} · {moment.tokens_used} tokens · {moment.porcentaje_usado}% del presupuesto"},
        crumbs=[("Inicio", reverse("portal:dashboard")), ("Conversaciones", reverse("portal:conversation_list")), (name, None)],
    )


# --------------------------------------------------------------------------
# Usuarios y roles
# --------------------------------------------------------------------------


@require("users", VIEW)
def user_list(request):
    qs = User.objects.filter(Q(is_superuser=True) | Q(portal_role__isnull=False)).select_related("portal_role__role").order_by("username")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    ctx = {
        "page": _page(request, qs), "q": q,
        "can_create": can(request.user, "users", CREATE),
        "can_edit": can(request.user, "users", EDIT),
        "can_delete": can(request.user, "users", DELETE),
    }
    return render(request, "portal/_user_table.html" if _htmx(request) else "portal/user_list.html", ctx)


def _user_guard(request, target, form):
    """Impide auto-bloqueo: no desactivarse/degradarse a sí mismo ni dejar el sistema sin super admin."""
    new_role = form.cleaned_data["role"]
    deactivating = not form.cleaned_data["is_active"]
    demoting = new_role.code != Role.SUPER_ADMIN and not target.is_superuser
    if (deactivating or demoting) and _is_last_super_admin(target):
        return "Debe quedar al menos un superadministrador activo."
    if target.pk == request.user.pk and deactivating:
        return "No puedes desactivar tu propia cuenta."
    return None


def user_form(request, pk=None):
    if not is_portal_user(request.user):
        return _need_login(request)
    if not can(request.user, "users", EDIT if pk else CREATE):
        raise PermissionDenied
    target = get_object_or_404(User, pk=pk) if pk else None
    form = UserForm((request.POST if request.method == "POST" else None), instance=target)
    if request.method == "POST" and form.is_valid():
        problem = _user_guard(request, target, form) if target else None
        if problem:
            form.add_error(None, problem)
        else:
            saved = form.save()
            audit.log(request, "create" if not pk else "edit", "users", saved, f"rol: {form.cleaned_data['role']}" + (" · contraseña restablecida" if form.cleaned_data.get("password") else ""))
            messages.success(request, "Usuario guardado.")
            return _done(request, reverse("portal:user_list"))
    return _panel(
        request, title="Editar usuario" if target else "Nuevo usuario", body="portal/_body_fields.html", form=form,
        crumbs=[("Inicio", reverse("portal:dashboard")), ("Usuarios", reverse("portal:user_list")), (target.username if target else "Nuevo", None)],
        ctx={"autocomplete_off": True},
    )


@require("users", DELETE)
@require_POST
def user_delete(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        messages.error(request, "No puedes eliminar tu propia cuenta.")
    elif _is_last_super_admin(target):
        messages.error(request, "Debe quedar al menos un superadministrador activo.")
    else:
        label = target.get_username()
        target.delete()
        audit.log(request, "delete", "users", label)
        messages.success(request, "Usuario eliminado.")
    return redirect("portal:user_list")


@require("roles", VIEW)
def role_list(request):
    roles = Role.objects.prefetch_related("permissions").all()
    return render(request, "portal/role_list.html", {
        "roles": [{"role": r, "perm_count": len(ALL_PERMISSIONS) if r.code == Role.SUPER_ADMIN else r.permissions.count(), "users": r.user_roles.count()} for r in roles],
        "can_create": can(request.user, "roles", CREATE),
        "can_edit": can(request.user, "roles", EDIT),
        "can_delete": can(request.user, "roles", DELETE),
        "total": len(ALL_PERMISSIONS),
    })


def role_create(request):
    if not is_portal_user(request.user):
        return _need_login(request)
    if not can(request.user, "roles", CREATE):
        raise PermissionDenied
    form = RoleForm((request.POST if request.method == "POST" else None))
    if request.method == "POST" and form.is_valid():
        role = form.save()
        audit.log(request, "create", "roles", role)
        messages.success(request, "Rol creado. Asígnale permisos.")
        return _done(request, reverse("portal:role_list"))
    return _panel(
        request, title="Nuevo rol", body="portal/_body_fields.html", form=form, submit="Crear rol",
        crumbs=[("Inicio", reverse("portal:dashboard")), ("Roles y permisos", reverse("portal:role_list")), ("Nuevo", None)],
    )


def role_matrix(request, pk):
    if not is_portal_user(request.user):
        return _need_login(request)
    if not can(request.user, "roles", VIEW):
        raise PermissionDenied
    role = get_object_or_404(Role, pk=pk)
    locked = role.code == Role.SUPER_ADMIN
    editable = can(request.user, "roles", EDIT) and not locked

    if request.method == "POST":
        if not editable:
            raise PermissionDenied
        wanted = {tuple(v.split(":", 1)) for v in request.POST.getlist("perm") if ":" in v} & ALL_PERMISSIONS
        with transaction.atomic():
            RolePermission.objects.filter(role=role).delete()
            RolePermission.objects.bulk_create(RolePermission(role=role, resource=r, action=a) for r, a in sorted(wanted))
        audit.log(request, "edit_matrix", "roles", role, f"{len(wanted)} permisos")
        messages.success(request, "Permisos actualizados.")
        return _done(request, reverse("portal:role_list"))

    granted = ALL_PERMISSIONS if locked else set(RolePermission.objects.filter(role=role).values_list("resource", "action"))
    matrix = [
        {"key": k, "label": label, "actions": [{"code": a, "label": al, "checked": (k, a) in granted} for a, al in acts.items()]}
        for k, (label, acts) in CATALOG.items()
    ]
    lead = ("El rol Superadministrador tiene todos los permisos y no se puede modificar." if locked
            else "Marca lo que este rol puede hacer. Los cambios aplican en la siguiente petición de cada usuario." if editable
            else "Solo lectura: no tienes permiso para editar la matriz.")
    return _panel(
        request, title=f"Permisos · {role.name}", body="portal/_body_matrix.html", submit="Guardar permisos" if editable else None, wide=True,
        ctx={"matrix": matrix, "editable": editable, "lead": lead},
        crumbs=[("Inicio", reverse("portal:dashboard")), ("Roles y permisos", reverse("portal:role_list")), (role.name, None)],
    )


@require("roles", DELETE)
@require_POST
def role_delete(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if role.is_system:
        messages.error(request, "Los roles de sistema no se pueden eliminar.")
    elif role.user_roles.exists():
        messages.error(request, "Hay usuarios con este rol; reasígnalos primero.")
    else:
        label = str(role)
        role.delete()
        audit.log(request, "delete", "roles", label)
        messages.success(request, "Rol eliminado.")
    return redirect("portal:role_list")
