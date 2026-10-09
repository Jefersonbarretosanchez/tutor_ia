from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password

from .models import Role, UserRole
from .permissions import is_portal_user

User = get_user_model()


class PortalAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Usuario o contraseña incorrectos.",
        "no_access": "Esta cuenta no tiene acceso al portal.",
    }

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not is_portal_user(user):
            raise forms.ValidationError(self.error_messages["no_access"], code="no_access")


class UserForm(forms.ModelForm):
    role = forms.ModelChoiceField(queryset=Role.objects.all(), label="Rol")
    password = forms.CharField(
        required=False,
        label="Contraseña",
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="Al crear es obligatoria; al editar, vacía = no cambiar. El usuario deberá cambiarla en su primer ingreso.",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {"username": "Usuario", "first_name": "Nombre", "last_name": "Apellido", "email": "Correo electrónico", "is_active": "Cuenta activa"}
        help_texts = {"username": ""}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and hasattr(self.instance, "portal_role"):
            self.fields["role"].initial = self.instance.portal_role.role_id

    def clean_password(self):
        pwd = self.cleaned_data.get("password")
        if not self.instance.pk and not pwd:
            raise forms.ValidationError("Obligatoria al crear un usuario.")
        if pwd:
            validate_password(pwd, self.instance if self.instance.pk else None)
        return pwd

    def save(self, commit=True):
        user = super().save(commit=False)
        pwd = self.cleaned_data.get("password")
        if pwd:
            user.set_password(pwd)
        user.save()
        ur, _ = UserRole.objects.get_or_create(user=user, defaults={"role": self.cleaned_data["role"]})
        ur.role = self.cleaned_data["role"]
        if pwd:
            ur.must_change_password = True
        ur.save()
        return user


class ResetChatForm(forms.Form):
    refund = forms.BooleanField(
        required=False,
        label="Acreditar los tokens que consumió",
        help_text="Devuelve al estudiante los tokens gastados en lo que se va a borrar.",
    )


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ["code", "name", "description"]
        labels = {"code": "Código interno", "name": "Nombre", "description": "Descripción"}
        help_texts = {"code": "Solo minúsculas, números y guiones (por ejemplo: tutor-academico)."}


class CreditForm(forms.Form):
    tokens = forms.IntegerField(min_value=1, max_value=10_000_000, label="Tokens a acreditar")
    note = forms.CharField(max_length=200, label="Motivo")


class PasswordChangeForm(forms.Form):
    current = forms.CharField(widget=forms.PasswordInput, label="Contraseña actual")
    new = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), label="Nueva contraseña")
    confirm = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), label="Confirmar")

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_current(self):
        if not self.user.check_password(self.cleaned_data["current"]):
            raise forms.ValidationError("La contraseña actual no es correcta.")
        return self.cleaned_data["current"]

    def clean(self):
        data = super().clean()
        if data.get("new") and data["new"] != data.get("confirm"):
            self.add_error("confirm", "Las contraseñas no coinciden.")
        if data.get("new"):
            validate_password(data["new"], self.user)
        return data
