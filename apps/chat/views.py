import logging

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat.models import ChatMessage, ChatSession, PromptTemplate
from apps.chat.serializers import (
    ChatMessageSerializer,
    ChatSessionSerializer,
    MessageCreateSerializer,
    PromptTemplateSerializer,
    SessionStartSerializer,
)
from apps.chat.services import grades, token_ledger
from apps.chat.services.n8n_client import call_flow

logger = logging.getLogger(__name__)


class TemplateListView(ListAPIView):
    """Plantillas sugeridas para el curso del estudiante que hace el launch (+ las globales)."""

    serializer_class = PromptTemplateSerializer

    def get_queryset(self):
        course = self.request.user.enrollment.course
        return PromptTemplate.objects.filter(
            Q(course=course) | Q(course__isnull=True),
            is_active=True,
        ).order_by("order", "title")


class SessionStartView(APIView):
    """Crea (o reutiliza) una sesión de chat a partir de la plantilla elegida."""

    def post(self, request):
        serializer = SessionStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        enrollment = request.user.enrollment
        course = enrollment.course

        template = get_object_or_404(
            PromptTemplate.objects.filter(Q(course=course) | Q(course__isnull=True), is_active=True),
            pk=serializer.validated_data["template_id"],
        )

        session = ChatSession.objects.create(enrollment=enrollment, template=template)
        status_info = token_ledger.get_usage_status(enrollment)

        return Response(
            {
                "session": ChatSessionSerializer(session).data,
                "usage": status_info.as_dict(),
            },
            status=201,
        )


class MessageCreateView(APIView):
    """Recibe el mensaje del estudiante, llama al agente en n8n y aplica el control de tokens."""

    def post(self, request, session_id):
        enrollment = request.user.enrollment
        session = get_object_or_404(ChatSession, pk=session_id, enrollment=enrollment)

        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        text = serializer.validated_data["message"]

        # 1) Verificar el límite ANTES de gastar una ejecución del agente.
        if not token_ledger.has_capacity(enrollment):
            status_info = token_ledger.get_usage_status(enrollment)
            return Response(
                {
                    "error": "Alcanzaste el límite de uso del chat para este curso.",
                    "code": "token_limit_reached",
                    "usage": status_info.as_dict(),
                },
                status=403,
            )

        history = list(
            session.messages.order_by("-created_at").values("role", "content")[: settings.CHAT_HISTORY_TURNS]
        )
        history.reverse()

        user_message = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content=text)

        result = call_flow(
            session.template.n8n_flow,
            user_id=enrollment.student.canvas_user_id or enrollment.student.sub,
            course_id=enrollment.course.canvas_course_id or enrollment.course.context_id,
            momento_tipo=session.template.momento_tipo,
            message=text,
            session_id=session.pk,
            history=[{"role": h["role"], "content": h["content"]} for h in history],
        )
        # (Si call_flow lanza N8nError, el exception_handler global de DRF
        # la convierte en un 502 — y como registrar la fila del ledger
        # ocurre después de esta línea, no se descuentan tokens.)

        assistant_message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            content=result["reply"],
            tokens_prompt=result["tokens"]["prompt"],
            tokens_completion=result["tokens"]["completion"],
            tokens_total=result["tokens"]["total"],
            n8n_execution_id=result["execution_id"],
            latency_ms=result["latency_ms"],
        )

        status_info = token_ledger.register_usage(enrollment, assistant_message, result["tokens"]["total"])

        if status_info.blocked:
            session.status = ChatSession.STATUS_LIMITED
            session.save(update_fields=["status"])

        if result.get("completed") and not enrollment.graded_at:
            grades.mark_activity_completed(enrollment)

        return Response(
            {
                "message": ChatMessageSerializer(assistant_message).data,
                "usage": status_info.as_dict(),
            },
            status=201,
        )
