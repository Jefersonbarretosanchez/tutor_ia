from rest_framework import serializers

from apps.chat.models import ClaraMessage, ClaraMoment


class ClaraMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClaraMessage
        fields = ["id", "role", "content", "created_at"]


class ClaraMomentSerializer(serializers.ModelSerializer):
    messages = ClaraMessageSerializer(many=True, read_only=True)

    class Meta:
        model = ClaraMoment
        fields = [
            "id",
            "momento",
            "mensajes_usados",
            "limite",
            "tokens_used",
            "porcentaje_usado",
            "presupuesto",
            "puede_avanzar",
            "messages",
        ]


class ClaraReplyCreateSerializer(serializers.Serializer):
    momento = serializers.ChoiceField(choices=ClaraMoment.MOMENTO_CHOICES)
    message = serializers.CharField(max_length=2000, trim_whitespace=True)

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError("El mensaje no puede estar vacío.")
        return value.strip()
