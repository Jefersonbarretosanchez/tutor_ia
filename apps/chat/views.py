import logging

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat.models import ChatMessage, ChatSession, ClaraMessage, ClaraMoment, PromptTemplate
from apps.chat.serializers import (
    ChatMessageSerializer,
    ChatSessionSerializer,
    ClaraMessageSerializer,
    ClaraMomentSerializer,
    ClaraReplyCreateSerializer,
    MessageCreateSerializer,
    PromptTemplateSerializer,
    SessionStartSerializer,
)
from apps.chat.services import canvas_pages, grades, token_ledger
from apps.chat.services.clara_client import ClaraError, call_apertura, call_responder
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


class ClaraMomentView(APIView):
    """
    Abre (o reutiliza) el momento de Clara para la página/unidad actual.

    La primera vez que un estudiante entra a un momento se llama a
    `/clara/apertura` y se guarda la pregunta detonadora + el historial;
    en visitas siguientes a la misma página se devuelve lo ya guardado sin
    volver a llamar al webhook.
    """

    def get(self, request):
        momento = request.query_params.get("momento", "")
        if momento not in dict(ClaraMoment.MOMENTO_CHOICES):
            return Response({"error": "Falta un 'momento' válido."}, status=400)

        enrollment = request.user.enrollment
        moment, created = ClaraMoment.objects.get_or_create(enrollment=enrollment, momento=momento)

        if created:
            student = enrollment.student
            try:
                result = call_apertura(
                    user_id=student.canvas_user_id or student.sub,
                    course_id=settings.CLARA_COURSE_ID,
                    momento=momento,
                )
            except ClaraError:
                # No dejamos un registro incompleto: la próxima visita a
                # esta página debe poder reintentar la apertura.
                moment.delete()
                raise

            moment.pregunta_id = result["pregunta_id"]
            moment.mensajes_usados = result["mensajes_usados"]
            if result["limite"]:
                moment.limite = result["limite"]
            moment.save(update_fields=["pregunta_id", "mensajes_usados", "limite"])
            ClaraMessage.objects.create(
                moment=moment,
                role=ClaraMessage.ROLE_ASSISTANT,
                content=result["reply"],
                tokens_used=result["tokens_used"],
            )

        return Response(ClaraMomentSerializer(moment).data)


class ClaraReplyView(APIView):
    """Manda la respuesta del estudiante a `/clara/responder` y guarda el turno."""

    def post(self, request):
        serializer = ClaraReplyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        momento = serializer.validated_data["momento"]
        text = serializer.validated_data["message"]

        enrollment = request.user.enrollment
        moment = get_object_or_404(ClaraMoment, enrollment=enrollment, momento=momento)

        # El control del presupuesto por unidad (tokens) vive enteramente en
        # el flujo de n8n — Django siempre manda el mensaje y reacciona a lo
        # que n8n decida (`tipo: "limite_alcanzado"`), nunca corta antes ni
        # fabrica su propio mensaje de cierre.
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

        ClaraMessage.objects.create(moment=moment, role=ClaraMessage.ROLE_USER, content=text)

        student = enrollment.student
        result = call_responder(
            user_id=student.canvas_user_id or student.sub,
            course_id=settings.CLARA_COURSE_ID,
            momento=momento,
            message=text,
        )
        # (Si call_responder lanza ClaraError, el exception_handler global de
        # DRF la convierte en un 502 — como registrar el ledger ocurre
        # después de esta línea, no se descuentan tokens.)

        assistant_message = ClaraMessage.objects.create(
            moment=moment,
            role=ClaraMessage.ROLE_ASSISTANT,
            content=result["reply"],
            tokens_used=result["tokens_used"],
        )

        moment.mensajes_usados = result["mensajes_usados"]
        if result["limite"]:
            moment.limite = result["limite"]
        if result["tipo"] == "limite_alcanzado":
            # "limite_alcanzado" no trae porcentaje_usado/tokens_usados —
            # se fuerza a 100% (ya no queda presupuesto) en vez de conservar
            # el último valor conocido (que podía quedarse, p. ej., en 92%).
            moment.porcentaje_usado = 100
        else:
            if result["tokens_usados"] is not None:
                moment.tokens_used = result["tokens_usados"]
            if result["presupuesto"] is not None:
                moment.presupuesto = result["presupuesto"]
            if result["porcentaje_usado"] is not None:
                moment.porcentaje_usado = result["porcentaje_usado"]
        moment.puede_avanzar = result["puede_avanzar"]
        moment.save(
            update_fields=[
                "mensajes_usados",
                "limite",
                "tokens_used",
                "presupuesto",
                "porcentaje_usado",
                "puede_avanzar",
                "last_activity_at",
            ]
        )

        status_info = token_ledger.register_usage(enrollment, None, result["tokens_used"])

        if result["puede_avanzar"] and not enrollment.graded_at:
            grades.mark_activity_completed(enrollment)

        if result["puede_avanzar"] and not moment.page_unlocked_at:
            canvas_pages.unlock_page_for_student(moment)

        return Response(
            {
                "message": ClaraMessageSerializer(assistant_message).data,
                "tipo": result["tipo"],
                "puede_avanzar": result["puede_avanzar"],
                "mensajes_usados": moment.mensajes_usados,
                "limite": moment.limite,
                "tokens_used": moment.tokens_used,
                "porcentaje_usado": moment.porcentaje_usado,
                "presupuesto": moment.presupuesto,
                "usage": status_info.as_dict(),
            },
            status=201,
        )
