"""
Control de consumo de tokens por estudiante y curso.

Regla del documento de alcance (sección 7):
1. Antes de llamar a n8n: se compara el acumulado del ledger contra el
   límite del curso. Si ya está en el límite, ni siquiera se dispara la
   ejecución del agente.
2. Después de la respuesta: se inserta una fila en el ledger con los
   tokens reales que devolvió n8n.
3. Al superar el 100%, `CourseEnrollment.chat_enabled` pasa a False.
"""

from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from apps.chat.models import TokenUsageLedger


@dataclass
class UsageStatus:
    tokens_used: int
    limit: int
    remaining: int
    warning: bool
    blocked: bool

    def as_dict(self):
        return {
            "tokens_used": self.tokens_used,
            "limit": self.limit,
            "remaining": self.remaining,
            "warning": self.warning,
            "blocked": self.blocked,
        }


def get_usage_status(enrollment) -> UsageStatus:
    limit = enrollment.course.effective_token_limit
    used = TokenUsageLedger.total_for(enrollment)
    remaining = max(0, limit - used)
    warning_threshold = limit * settings.TOKEN_WARNING_THRESHOLD_PCT / 100
    return UsageStatus(
        tokens_used=used,
        limit=limit,
        remaining=remaining,
        warning=used >= warning_threshold,
        blocked=(not enrollment.chat_enabled) or used >= limit,
    )


def has_capacity(enrollment) -> bool:
    """Instructores nunca se bloquean; el resto se evalúa contra su ledger."""
    if enrollment.is_instructor:
        return True
    if not enrollment.chat_enabled:
        return False
    return get_usage_status(enrollment).remaining > 0 or TokenUsageLedger.total_for(enrollment) < enrollment.course.effective_token_limit


def register_usage(enrollment, message, tokens_total: int) -> UsageStatus:
    """Inserta la fila del ledger y, si corresponde, apaga el chat de esa matrícula."""
    TokenUsageLedger.objects.create(enrollment=enrollment, message=message, tokens_total=tokens_total)

    status = get_usage_status(enrollment)

    if enrollment.is_instructor:
        return status

    if status.tokens_used >= status.limit and enrollment.chat_enabled:
        enrollment.chat_enabled = False
        enrollment.limit_reached_at = timezone.now()
        enrollment.save(update_fields=["chat_enabled", "limit_reached_at"])
        status.blocked = True

    return status
