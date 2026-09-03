"""
Django settings for LTI Chat Scala.

Lee toda la configuración sensible desde variables de entorno (ver .env.example).
Diseñado para desplegarse sin Docker: Gunicorn + Nginx + PostgreSQL nativos en una VPS.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --------------------------------------------------------------------------
# Seguridad básica
# --------------------------------------------------------------------------

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-solo-para-desarrollo-local")

DEBUG = env_bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

# --------------------------------------------------------------------------
# Aplicaciones
# --------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "pylti1p3.contrib.django.lti1p3_tool_config",
    "apps.lti_tool",
    "apps.chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Reemplaza XFrameOptionsMiddleware por nuestra política basada en CSP
    # (ver LTI_FRAME_ANCESTORS más abajo): la LTI vive embebida en un iframe
    # de Canvas, así que no podemos usar DENY/SAMEORIGIN por defecto.
    "apps.lti_tool.middleware.LtiFrameAncestorsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --------------------------------------------------------------------------
# Base de datos — PostgreSQL en producción, sqlite por defecto en local
# --------------------------------------------------------------------------
# DATABASE_URL de ejemplo en prod:
#   postgres://lti_chat:CAMBIA_ESTO@127.0.0.1:5432/lti_chat_scala

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Internacionalización
# --------------------------------------------------------------------------

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Estáticos
# --------------------------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# OJO: se deja en AutoField (el default histórico de Django) a nivel
# global a propósito, porque pylti1p3.contrib.django.lti1p3_tool_config
# (app de terceros) shippea sus migraciones asumiendo AutoField — si este
# valor se sube a BigAutoField, cada `makemigrations` futuro propone
# alterar el id de esa app sin que nosotros hayamos tocado nada. Nuestras
# propias apps (lti_tool, chat) declaran BigAutoField explícitamente en su
# propio AppConfig.default_auto_field, así que no dependen de esto.
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.chat.auth.LaunchTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "EXCEPTION_HANDLER": "apps.chat.exceptions.chat_exception_handler",
}

# --------------------------------------------------------------------------
# Cache — usada por pylti1p3 para el estado del login OIDC (nonce/state) en
# vez de la sesión de Django, porque el navegador puede bloquear cookies de
# terceros dentro del iframe de Canvas. En producción usar Redis (todos los
# workers de Gunicorn deben compartir el mismo cache); en local, memoria.
# --------------------------------------------------------------------------

REDIS_URL = os.environ.get("REDIS_URL", "")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# --------------------------------------------------------------------------
# Token corto emitido tras validar el lanzamiento LTI (firma interna Django)
# --------------------------------------------------------------------------
# El widget de chat vive en un iframe de origen cruzado dentro de Canvas.
# No dependemos de la cookie de sesión de Django (los navegadores restringen
# cookies de terceros): en su lugar emitimos un JWT corto que el frontend
# manda como "Authorization: Bearer ..." en cada llamada a /api/.

LAUNCH_TOKEN_SECRET = os.environ.get("LAUNCH_TOKEN_SECRET", SECRET_KEY)
LAUNCH_TOKEN_TTL_SECONDS = int(os.environ.get("LAUNCH_TOKEN_TTL_SECONDS", 60 * 90))  # 90 min

# --------------------------------------------------------------------------
# LTI 1.3
# --------------------------------------------------------------------------
# Dominios de Canvas permitidos como frame-ancestors (separados por coma).
# Ej: https://tuinstitucion.instructure.com
LTI_FRAME_ANCESTORS = env_list("LTI_FRAME_ANCESTORS", "")

# Clave RSA propia de la herramienta (para firmar/exponer JWKS ante Canvas).
# Generar con: openssl genrsa -out lti_tool_private.pem 2048
LTI_TOOL_PRIVATE_KEY_PATH = os.environ.get("LTI_TOOL_PRIVATE_KEY_PATH", str(BASE_DIR / "keys" / "lti_tool_private.pem"))
LTI_TOOL_PUBLIC_KEY_PATH = os.environ.get("LTI_TOOL_PUBLIC_KEY_PATH", str(BASE_DIR / "keys" / "lti_tool_public.pem"))

# --------------------------------------------------------------------------
# Control de tokens del chat
# --------------------------------------------------------------------------

DEFAULT_COURSE_TOKEN_LIMIT = int(os.environ.get("DEFAULT_COURSE_TOKEN_LIMIT", 200_000))
TOKEN_WARNING_THRESHOLD_PCT = int(os.environ.get("TOKEN_WARNING_THRESHOLD_PCT", 80))
N8N_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("N8N_REQUEST_TIMEOUT_SECONDS", 40))
CHAT_HISTORY_TURNS = int(os.environ.get("CHAT_HISTORY_TURNS", 8))

# --------------------------------------------------------------------------
# Webhooks fijos de Clara (apertura de momento + turno de conversación) —
# ver apps/chat/services/clara_client.py.
# --------------------------------------------------------------------------

CLARA_APERTURA_URL = os.environ.get(
    "CLARA_APERTURA_URL", "https://scalalearning3.app.n8n.cloud/webhook/clara/apertura"
)
CLARA_RESPONDER_URL = os.environ.get(
    "CLARA_RESPONDER_URL", "https://scalalearning3.app.n8n.cloud/webhook/clara/responder"
)
CLARA_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("CLARA_REQUEST_TIMEOUT_SECONDS", 40))
# El "course_id" que reconoce el workflow de Clara en Supabase es un slug de
# contenido (p. ej. 'toma_decisiones' para el curso piloto), no el
# canvas_course_id de Canvas — se manda fijo hasta que haya más de un curso
# sembrado en Supabase con su propio slug.
CLARA_COURSE_ID = os.environ.get("CLARA_COURSE_ID", "toma_decisiones")

# --------------------------------------------------------------------------
# API REST de Canvas (para "Asignar acceso" de páginas) — ver
# apps/chat/services/canvas_pages.py. Es un token distinto del Developer
# Key LTI: requiere permiso de edición de curso (Personal Access Token o
# Developer Key OAuth2 propio), no solo scopes de LTI Advantage.
# --------------------------------------------------------------------------

CANVAS_API_BASE_URL = os.environ.get("CANVAS_API_BASE_URL", "https://uandinavirtual.instructure.com")
CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
CANVAS_API_TIMEOUT_SECONDS = int(os.environ.get("CANVAS_API_TIMEOUT_SECONDS", 15))

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} — {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {
        "apps.lti_tool": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "apps.chat": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}

# --------------------------------------------------------------------------
# Seguridad adicional en producción (activar vía .env cuando DEBUG=False)
# --------------------------------------------------------------------------

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
