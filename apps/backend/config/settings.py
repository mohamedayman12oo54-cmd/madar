"""
Django settings for the Madar backend.

Configuration is environment-driven (see .env.example) so the exact same
codebase runs safely in development and production — only the .env file
changes. Nothing sensitive is hard-coded here.
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    val = os.environ.get(name, default)
    return [item.strip() for item in val.split(",") if item.strip()]


# ---------------------------------------------------------------- core ----
# SECURITY WARNING: keep the secret key used in production secret, and set
# it via the DJANGO_SECRET_KEY environment variable — never commit a real
# one. This fallback only exists so `runserver` doesn't crash if .env is
# missing, and it deliberately still forces DEBUG-only behaviour below.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-only-key-do-not-use-in-production")

DEBUG = env_bool("DJANGO_DEBUG", default=False)

if SECRET_KEY == "insecure-dev-only-key-do-not-use-in-production" and not DEBUG:
    raise RuntimeError(
        "DJANGO_SECRET_KEY is not set. Refusing to start with DEBUG=False and the "
        "placeholder secret key — set DJANGO_SECRET_KEY in your environment/.env file."
    )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")


# ------------------------------------------------------------ apps/mw -----
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "accounts",
    "environments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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


# --------------------------------------------------------------- data -----
# SQLite by default (zero setup for dev/small deployments). Point
# DATABASE_URL-style vars at Postgres in production if you like — kept
# simple/explicit here rather than pulling in another dependency.
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("DB_NAME", BASE_DIR / "db.sqlite3"),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", ""),
        "PORT": os.environ.get("DB_PORT", ""),
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "accounts.validators.MadarPasswordValidator"},
]


# ------------------------------------------------------------- i18n/tz ----
LANGUAGE_CODE = "ar"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Africa/Cairo")
USE_I18N = True
USE_TZ = True


# ------------------------------------------------------------- static -----
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------- DRF / JWT ------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Secure by default: every view requires auth unless it explicitly
    # opts out (AllowAny) — so a forgotten permission_classes never
    # accidentally exposes an endpoint.
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        # Brute-force protection on credential guessing.
        "login": "10/min",
        # OTP endpoints: expensive to abuse (SMS cost / spam), so tighter.
        "otp-request": "5/hour",
        "otp-verify": "10/hour",
        # Generic fallback for other sensitive-but-unauthenticated writes.
        "sensitive": "20/hour",
    },
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PARSER_CLASSES": ("rest_framework.parsers.JSONParser",),
    "EXCEPTION_HANDLER": "config.exceptions.api_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}


# ------------------------------------------------------------- CORS -------
# Explicit allow-list only — never a wildcard, since that would let any
# website read API responses on a logged-in user's behalf if credentials
# were ever involved. We use header-based JWT (no cookies), so credentials
# stay off too.
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
CORS_ALLOW_CREDENTIALS = False


# --------------------------------------------------------- security -------
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

# HTTPS-only hardening — left off in DEBUG so local http:// dev keeps working.
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=not DEBUG)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

# Dev-only convenience: return the generated OTP code in API responses so
# the whole flow is testable without a real SMS/email provider wired up.
# This is automatically impossible to enable in production because it's
# hard-gated on DEBUG, not just on the env var.
EXPOSE_OTP_IN_RESPONSE = DEBUG and env_bool("EXPOSE_OTP_IN_RESPONSE", default=True)


# ------------------------------------------------------------ logging -----
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING" if not DEBUG else "INFO", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
