from rest_framework import serializers

from apps.chat.models import ChatMessage, ChatSession, ClaraMessage, ClaraMoment, PromptTemplate


class PromptTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptTemplate
        fields = ["id", "momento_tipo", "title", "description"]


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "role", "content", "created_at"]


class ChatSessionSerializer(serializers.ModelSerializer):
    template = PromptTemplateSerializer(read_only=True)

    class Meta:
        model = ChatSession
        fields = ["id", "template", "status", "started_at"]


class SessionStartSerializer(serializers.Serializer):
    template_id = serializers.IntegerField()


class MessageCreateSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000, trim_whitespace=True)

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError("El mensaje no puede estar vacío.")
        return value.strip()


class ClaraMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClaraMessage
        fields = ["id", "role", "content", "created_at"]


class ClaraMomentSerializer(serializers.ModelSerializer):
    messages = ClaraMessageSerializer(many=True, read_only=True)

    class Meta:
        model = ClaraMoment
        fields = ["id", "momento", "mensajes_usados", "limite", "puede_avanzar", "messages"]


class ClaraReplyCreateSerializer(serializers.Serializer):
    momento = serializers.ChoiceField(choices=ClaraMoment.MOMENTO_CHOICES)
    message = serializers.CharField(max_length=2000, trim_whitespace=True)

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError("El mensaje no puede estar vacío.")
        return value.strip()
