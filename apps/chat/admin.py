from django.contrib import admin

from apps.chat.models import (
    ChatMessage,
    ChatSession,
    ClaraMessage,
    ClaraMoment,
    N8nFlow,
    PromptTemplate,
    TokenUsageLedger,
)


@admin.register(N8nFlow)
class N8nFlowAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "webhook_url", "is_active")
    list_filter = ("is_active",)


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ("title", "momento_tipo", "course", "n8n_flow", "order", "is_active")
    list_filter = ("momento_tipo", "is_active", "course")


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = [f.name for f in ChatMessage._meta.fields]
    can_delete = False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "enrollment", "template", "status", "started_at")
    list_filter = ("status", "template")
    inlines = [ChatMessageInline]


class ClaraMessageInline(admin.TabularInline):
    model = ClaraMessage
    extra = 0
    readonly_fields = [f.name for f in ClaraMessage._meta.fields]
    can_delete = False


@admin.register(ClaraMoment)
class ClaraMomentAdmin(admin.ModelAdmin):
    list_display = ("id", "enrollment", "momento", "mensajes_usados", "limite", "puede_avanzar", "last_activity_at")
    list_filter = ("momento", "puede_avanzar")
    inlines = [ClaraMessageInline]


@admin.register(TokenUsageLedger)
class TokenUsageLedgerAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "tokens_total", "created_at", "note")
    list_filter = ("enrollment__course",)
    readonly_fields = [f.name for f in TokenUsageLedger._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False
