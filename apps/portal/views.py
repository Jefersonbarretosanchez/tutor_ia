from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError, Q, Sum
from django.forms import modelform_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.chat.models import ClaraMoment, TokenUsageLedger
from apps.chat.services import canvas_pages
from apps.lti_tool.models import Course, CourseEnrollment, CoursePageGate, LtiLaunchLog

from . import audit
from .forms import CreditForm, PasswordChangeForm, PortalAuthenticationForm, RoleForm, UserForm
from .models import Role, RolePermission, UserRole
from .permissions import ALL_PERMISSIONS, CATALOG, DELETE, EDIT, CREATE, VIEW, can, is_portal_user, require
from .registry import RESOURCES

User = get_user_model()

PAGE_SIZE = 25
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 15 * 60


def _page(request, qs):
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    page.qs = params.urlencode() + "&" if params else ""
    return page


def _htmx(request):
    return request.headers.get("HX-Request") == "true"


def _is_last_super_admin(user):
    """True si `user` es el único super admin activo (no se puede quitar/desactivar)."""
    def is_super(u):
        return u.is_superuser or (hasattr(u, "portal_role") and u.portal_role.role.code == Role.SUPER_ADMIN)

    if not is_super(user):
        return False
    others = [u for u in User.objects.filter(is_active=True).exclude(pk=user.pk).select_related("portal_role__role") if is_super(u)]
    return not others


# --------------------------------------------------------------------------
# Autenticación
# --------------------------------------------------------------------------


def login_view(request):
    if is_portal_user(request.user):
        return redirect("portal:dashboard")

    form = PortalAuthenticationForm(request, data=request.POST or None)
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
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        request.user.set_password(form.cleaned_data["new"])
        request.user.save()
        UserRole.objects.filter(user=request.user).update(must_change_password=False)
        update_session_auth_hash(request, request.user)
        audit.log(request, "password_change", "auth", request.user)
        messages.success(request, "Contraseña actualizada.")
        return redirect("portal:dashboard")
    forced = hasattr(request.user, "portal_role") and request.user.portal_role.must_change_password
    return render(request, "portal/password_change.html", {"form": form, "forced": forced})


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------


def dashboard(request):
    if not is_portal_user(request.user):
        return redirect_to_login(request.get_full_path(), "portal:login")
    enrollments = CourseEnrollment.objects.filter(is_instructor=False)
    ctx = {
        "courses": Course.objects.filter(is_active=True).count(),
        "students": enrollments.count(),
        "blocked": enrollments.filter(chat_enabled=False).count(),
        "tokens": TokenUsageLedger.objects.aggregate(t=Sum("tokens_total"))["t"] or 0,
        "can_logs": can(request.user, "launch_logs", VIEW),
    }
    if ctx["can_logs"]:
        ctx["failed_launches"] = LtiLaunchLog.objects.filter(validated=False).order_by("-created_at")[:5]
    return render(request, "portal/dashboard.html", ctx)


# --------------------------------------------------------------------------
# Recursos genéricos (cursos, gates, flujos, prompts, y listados de solo lectura)
# --------------------------------------------------------------------------


def _resource(key):
    try:
        return RESOURCES[key]
    except KeyError:
        raise Http404


def _cells(res, obj):
    out = []
    for _, col in res.columns:
        out.append(col(obj) if callable(col) else getattr(obj, col))
    return out


def resource_list(request, key):
    res = _resource(key)
    if not is_portal_user(request.user):
        return redirect_to_login(request.get_full_path(), "portal:login")
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
        return redirect("portal:login")
    if not res.fields or not can(request.user, key, action) or (not pk and not res.can_create):
        raise PermissionDenied

    obj = get_object_or_404(res.model, pk=pk) if pk else None
    form_cls = res.form_class or modelform_factory(res.model, fields=res.fields)
    form = form_cls(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        changed = ", ".join(f for f in form.changed_data if f != "shared_secret") or "—"
        audit.log(request, "create" if not pk else "edit", key, saved, f"campos: {changed}")
        messages.success(request, "Guardado correctamente.")
        return redirect("portal:resource_list", key=key)
    return render(request, "portal/resource_form.html", {"res": res, "form": form, "obj": obj})


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
# Matrículas (reactivar chat, créditos)
# --------------------------------------------------------------------------


def _enrollment_row(e):
    used = e.used or 0
    limit = e.course.effective_token_limit
    return {"e": e, "used": used, "limit": limit, "pct": min(100, round(used * 100 / limit)) if limit else 0}


def _enrollment_qs():
    return CourseEnrollment.objects.select_related("student", "course").annotate(used=Sum("token_ledger__tokens_total"))


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
    ctx = {
        "page": page, "rows": [_enrollment_row(e) for e in page], "q": q, "status": status, "course": course,
        "courses": Course.objects.all(),
        "can_reactivate": can(request.user, "enrollments", "reactivate"),
        "can_adjust": can(request.user, "ledger", "adjust"),
        "credit_form": CreditForm(),
    }
    return render(request, "portal/_enrollment_table.html" if _htmx(request) else "portal/enrollment_list.html", ctx)


def _render_row(request, pk, **extra):
    e = get_object_or_404(_enrollment_qs(), pk=pk)
    ctx = {
        "r": _enrollment_row(e),
        "can_reactivate": can(request.user, "enrollments", "reactivate"),
        "can_adjust": can(request.user, "ledger", "adjust"),
        "credit_form": extra.pop("credit_form", CreditForm()),
        **extra,
    }
    return render(request, "portal/_enrollment_row.html", ctx)


@require("enrollments", "reactivate")
@require_POST
def enrollment_reactivate(request, pk):
    e = get_object_or_404(CourseEnrollment, pk=pk)
    e.chat_enabled = True
    e.limit_reached_at = None
    e.save(update_fields=["chat_enabled", "limit_reached_at"])
    audit.log(request, "reactivate_chat", "enrollments", e)
    return _render_row(request, pk, flash="Chat reactivado.")


@require("ledger", "adjust")
@require_POST
def enrollment_credit(request, pk):
    e = get_object_or_404(CourseEnrollment.objects.select_related("course"), pk=pk)
    form = CreditForm(request.POST)
    if not form.is_valid():
        return _render_row(request, pk, credit_form=form, flash="Revisa el formulario de crédito.", open_credit=True)
    tokens = form.cleaned_data["tokens"]
    note = f"Crédito manual ({request.user.get_username()}): {form.cleaned_data['note']}"[:255]
    with transaction.atomic():
        TokenUsageLedger.objects.create(enrollment=e, tokens_total=-tokens, note=note)
        used = TokenUsageLedger.total_for(e)
        if not e.chat_enabled and e.limit_reached_at and used < e.course.effective_token_limit:
            e.chat_enabled = True
            e.limit_reached_at = None
            e.save(update_fields=["chat_enabled", "limit_reached_at"])
    audit.log(request, "credit_tokens", "ledger", e, f"-{tokens} tokens · {form.cleaned_data['note']}")
    return _render_row(request, pk, flash=f"{tokens:,} tokens acreditados.")


# --------------------------------------------------------------------------
# Conversaciones (solo lectura)
# --------------------------------------------------------------------------


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
    return render(request, "portal/conversation_detail.html", {"m": moment, "msgs": moment.messages.order_by("created_at")})


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


def _user_guard(request, target, form=None):
    """Impide auto-bloqueo: no desactivarse/degradarse a sí mismo ni dejar el sistema sin super admin."""
    if form is None:
        return None
    new_role = form.cleaned_data["role"]
    deactivating = not form.cleaned_data["is_active"]
    demoting = new_role.code != Role.SUPER_ADMIN and not target.is_superuser
    if (deactivating or demoting) and _is_last_super_admin(target):
        return "Debe quedar al menos un super admin activo."
    if target.pk == request.user.pk and deactivating:
        return "No puedes desactivar tu propia cuenta."
    return None


def user_form(request, pk=None):
    if not is_portal_user(request.user):
        return redirect("portal:login")
    action = EDIT if pk else CREATE
    if not can(request.user, "users", action):
        raise PermissionDenied
    target = get_object_or_404(User, pk=pk) if pk else None
    form = UserForm(request.POST or None, instance=target)
    if request.method == "POST" and form.is_valid():
        problem = _user_guard(request, target, form) if target else None
        if problem:
            form.add_error(None, problem)
        else:
            saved = form.save()
            audit.log(request, "create" if not pk else "edit", "users", saved, f"rol: {form.cleaned_data['role']}" + (" · contraseña restablecida" if form.cleaned_data.get("password") else ""))
            messages.success(request, "Usuario guardado.")
            return redirect("portal:user_list")
    return render(request, "portal/user_form.html", {"form": form, "target": target})


@require("users", DELETE)
@require_POST
def user_delete(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        messages.error(request, "No puedes eliminar tu propia cuenta.")
    elif _is_last_super_admin(target):
        messages.error(request, "Debe quedar al menos un super admin activo.")
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
        "can_delete": can(request.user, "roles", DELETE),
        "total": len(ALL_PERMISSIONS),
    })


def role_create(request):
    if not is_portal_user(request.user):
        return redirect("portal:login")
    if not can(request.user, "roles", CREATE):
        raise PermissionDenied
    form = RoleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        role = form.save()
        audit.log(request, "create", "roles", role)
        messages.success(request, "Rol creado. Asígnale permisos.")
        return redirect("portal:role_matrix", pk=role.pk)
    return render(request, "portal/role_form.html", {"form": form})


def role_matrix(request, pk):
    if not is_portal_user(request.user):
        return redirect("portal:login")
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
        messages.success(request, "Matriz de permisos actualizada.")
        return redirect("portal:role_matrix", pk=role.pk)

    granted = ALL_PERMISSIONS if locked else set(RolePermission.objects.filter(role=role).values_list("resource", "action"))
    matrix = [
        {"key": k, "label": label, "actions": [{"code": a, "label": al, "checked": (k, a) in granted} for a, al in acts.items()]}
        for k, (label, acts) in CATALOG.items()
    ]
    return render(request, "portal/role_matrix.html", {"role": role, "matrix": matrix, "locked": locked, "editable": editable})


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
