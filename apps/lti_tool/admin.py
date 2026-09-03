from django.contrib import admin

from apps.chat.services import canvas_pages

from .models import Course, CourseEnrollment, CoursePageGate, LtiLaunchLog, Student


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "context_id",
        "lti_tool",
        "token_limit",
        "show_course_token_usage",
        "show_unit_token_count",
        "is_active",
        "ags_enabled",
    )
    list_filter = ("is_active", "lti_tool")
    search_fields = ("title", "context_id", "canvas_course_id")

    @admin.display(boolean=True, description="AGS")
    def ags_enabled(self, obj):
        return bool(obj.ags_lineitems_url)


@admin.register(CoursePageGate)
class CoursePageGateAdmin(admin.ModelAdmin):
    list_display = ("course", "momento", "canvas_page_url", "locked_at")
    list_filter = ("course",)
    search_fields = ("canvas_page_url", "momento")
    actions = ["bloquear_pagina_ahora"]

    @admin.action(description="Bloquear página ahora (only_visible_to_overrides)")
    def bloquear_pagina_ahora(self, request, queryset):
        ok = sum(1 for gate in queryset if canvas_pages.lock_page(gate))
        self.message_user(request, f"{ok}/{queryset.count()} página(s) bloqueada(s) correctamente.")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "login_id", "canvas_user_id", "sub", "lti_tool", "created_at")
    search_fields = ("name", "email", "login_id", "canvas_user_id", "sub")


@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "section_ids", "chat_enabled", "is_instructor", "limit_reached_at", "graded_at")
    list_filter = ("chat_enabled", "is_instructor", "course")
    actions = ["reactivar_chat"]

    @admin.action(description="Reactivar chat para las matrículas seleccionadas")
    def reactivar_chat(self, request, queryset):
        queryset.update(chat_enabled=True, limit_reached_at=None)


@admin.register(LtiLaunchLog)
class LtiLaunchLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "validated", "issuer", "sub", "ip_address")
    list_filter = ("validated",)
    readonly_fields = [f.name for f in LtiLaunchLog._meta.fields]

    def has_add_permission(self, request):
        return False
