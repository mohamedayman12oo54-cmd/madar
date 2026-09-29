"""
Django settings for the Madar backend.

Configuration is environment-driven (see .env.example) so the exact same
codebase runs safely in development and production — only the .env file
changes. Nothing sensitive is hard-coded here.
"""
import os
import sys
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from corsheaders.defaults import default_headers
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_str(name, default=""):
    """Like os.environ.get, but a blank value (`NAME=` in a .env file) counts as
    unset — otherwise an empty line silently overrides a safe default."""
    val = os.environ.get(name)
    return default if val is None or not val.strip() else val.strip()


def env_bool(name, default=False):
    val = env_str(name, "")
    if not val:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    val = env_str(name, default)
    return [item.strip() for item in val.split(",") if item.strip()]


def env_int(name, default):
    val = os.environ.get(name)
    if val is None or not val.strip():
        return default
    try:
        return int(val)
    except ValueError:
        raise ImproperlyConfigured(f"{name} must be an integer, got {val!r}.")


# ---------------------------------------------------------------- core ----
# SECURITY WARNING: keep the secret key used in production secret, and set
# it via the DJANGO_SECRET_KEY environment variable — never commit a real
# one. The fallback only exists so `runserver` works in DEBUG without a .env.
_DEV_SECRET_KEY = "insecure-dev-only-key-do-not-use-in-production"
SECRET_KEY = env_str("DJANGO_SECRET_KEY", _DEV_SECRET_KEY)

DEBUG = env_bool("DJANGO_DEBUG", default=False)


# ------------------------------------------------- production guard rails --
# With DEBUG off the app refuses to start on configuration that is unsafe by
# construction, instead of booting and relying on someone reading a warning.
_PLACEHOLDER_PREFIXES = ("change-me", "changeme", "insecure", "your-", "secret")


def _https_only(name, values):
    bad = [v for v in values if v == "*" or not v.startswith("https://")]
    if bad:
        raise ImproperlyConfigured(
            f"{name} must contain only https:// origins when DJANGO_DEBUG is off "
            f"(offending: {bad})."
        )


if not DEBUG:
    if (
        SECRET_KEY == _DEV_SECRET_KEY
        or SECRET_KEY.lower().startswith(_PLACEHOLDER_PREFIXES)
        or len(SECRET_KEY) < 50
        or len(set(SECRET_KEY)) < 8
    ):
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is missing, a placeholder, or too weak (need >= 50 chars, "
            "not a 'change-me' style value). Generate one with: "
            'python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"'
        )


# In production there is no localhost default: the host list must be explicit.
ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    "localhost,127.0.0.1" if DEBUG else "",
)

if not DEBUG and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must list explicit hostnames "
        "(no '*', not empty) when DJANGO_DEBUG is off."
    )


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
    "academics",
    "scheduling",
    "financials",
    "evaluation",
    "notifications",
    "content",
    "ai",
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
        "ENGINE": env_str(
            "DB_ENGINE",
            "django.db.backends.sqlite3",
        ),
        "NAME": env_str(
            "DB_NAME",
            str(BASE_DIR / "db.sqlite3"),
        ),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", ""),
        "PORT": os.environ.get("DB_PORT", ""),
    }
}


# ------------------------------------------------------------- cache -------
# Throttle counters (accounts/throttles.py) live in the cache, so the cache
# must be SHARED by every web worker or each worker enforces its own limit
# (and a restart wipes it). Django's built-in database cache satisfies that
# with no new dependency: run `python manage.py createcachetable` once per
# deployment. Local dev and the test suite use in-process memory.
CACHE_BACKEND = env_str(
    "DJANGO_CACHE_BACKEND",
    "locmem" if DEBUG else "db",
).lower()

if "test" in sys.argv or CACHE_BACKEND == "locmem":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "madar-local",
        }
    }

elif CACHE_BACKEND == "db":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "madar_cache",
        }
    }

else:
    raise ImproperlyConfigured(
        "DJANGO_CACHE_BACKEND must be 'db' or 'locmem'."
    )


# Which ai/providers.py implementation the worker uses. Only "stub" exists —
# no LLM credentials are configured anywhere in this project.
AI_PROVIDER = env_str("AI_PROVIDER", "stub")


AUTH_USER_MODEL = "accounts.User"


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME":
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME":
            "django.contrib.auth.password_validation.CommonPasswordValidator"
    },
    {
        "NAME":
            "accounts.validators.MadarPasswordValidator"
    },
]


# ------------------------------------------------------------- i18n/tz ----
LANGUAGE_CODE = "ar"

TIME_ZONE = env_str(
    "DJANGO_TIME_ZONE",
    "Africa/Cairo",
)

USE_I18N = True
USE_TZ = True


# ------------------------------------------------------------- static -----
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------- DRF / JWT ------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # SimpleJWT + session_version check (revoked sessions stop working
        # immediately) — see accounts/authentication.py.
        "accounts.authentication.MadarJWTAuthentication",
    ),

    # Secure by default: every view requires auth unless it explicitly
    # opts out (AllowAny) — so a forgotten permission_classes never
    # accidentally exposes an endpoint.
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),

    # Throttles are attached explicitly, per view (accounts/throttles.py).
    "DEFAULT_THROTTLE_CLASSES": (),

    "DEFAULT_THROTTLE_RATES": {
        # --- per client IP ---
        "login": "10/min",
        "otp-request": "5/hour",
        "otp-verify": "10/hour",
        "sensitive": "20/hour",

        # --- per submitted identifier (phone/email), any number of IPs ---
        "login-account": "20/hour",
        "otp-target": "5/hour",

        # --- per authenticated user ---
        "student-add": "300/hour",
        "ai-submit": "30/hour",
    },

    # How many reverse proxies sit in front of Django and append to
    # X-Forwarded-For. 0 (default) means "trust none": the header is ignored
    # and the socket address is the client IP, so it cannot be spoofed to
    # dodge throttling. Set DJANGO_NUM_PROXIES=N only when N trusted proxies
    # really append the real client address.
    "NUM_PROXIES": env_int(
        "DJANGO_NUM_PROXIES",
        0,
    ),

    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),

    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
    ),

    # Phase 2+ tenant-scoped list endpoints (Grade/Group/Session/...) get
    # pagination for free by using generics/viewsets. The current teacher/
    # student environment lists are plain APIViews and stay unpaginated on
    # purpose (see environments/tenancy.py:StandardPagination).
    "DEFAULT_PAGINATION_CLASS":
        "environments.tenancy.StandardPagination",

    "EXCEPTION_HANDLER":
        "config.exceptions.api_exception_handler",

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
    "http://localhost:5173,http://127.0.0.1:5173" if DEBUG else "",
)

CORS_ALLOW_CREDENTIALS = False


# Custom header sent by the Madar frontend to identify
# the active environment/tenant.
CORS_ALLOW_HEADERS = [
    *default_headers,
    "x-madar-environment",
]


CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "",
)


if not DEBUG:
    _https_only(
        "CORS_ALLOWED_ORIGINS",
        CORS_ALLOWED_ORIGINS,
    )

    _https_only(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        CSRF_TRUSTED_ORIGINS,
    )


# --------------------------------------------------------- security -------
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"


# Request bodies are small JSON documents (Phase 5 file handling will set its
# own, separate limits). An explicit cap keeps oversized JSON from being
# buffered in memory.
DATA_UPLOAD_MAX_MEMORY_SIZE = 1_000_000


# HTTPS-only hardening — left off in DEBUG so local http:// dev keeps working.
SECURE_SSL_REDIRECT = env_bool(
    "DJANGO_SECURE_SSL_REDIRECT",
    default=not DEBUG,
)

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

SESSION_COOKIE_HTTPONLY = True

CSRF_COOKIE_HTTPONLY = True
# Django admin only; the API uses Bearer tokens, not cookies

SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_HSTS_SECONDS = (
    0
    if DEBUG
    else env_int(
        "DJANGO_HSTS_SECONDS",
        60 * 60 * 24 * 30,
    )
)

SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "DJANGO_HSTS_INCLUDE_SUBDOMAINS",
    default=not DEBUG,
)

SECURE_HSTS_PRELOAD = env_bool(
    "DJANGO_HSTS_PRELOAD",
    default=not DEBUG,
)


# Behind a TLS-terminating reverse proxy Django only sees plain HTTP, so
# SECURE_SSL_REDIRECT would redirect forever unless it can learn the original
# scheme. Only enable this when the proxy OVERWRITES X-Forwarded-Proto (never
# passes a client-supplied value through) — otherwise clients could forge it.
if env_bool(
    "DJANGO_BEHIND_TLS_PROXY",
    default=False,
):
    SECURE_PROXY_SSL_HEADER = (
        "HTTP_X_FORWARDED_PROTO",
        "https",
    )


# Dev-only convenience: return the generated OTP code in API responses so
# the whole flow is testable without a real SMS/email provider wired up.
# Hard-gated on DEBUG, so it cannot be enabled in production by an env var.
EXPOSE_OTP_IN_RESPONSE = (
    DEBUG
    and env_bool(
        "EXPOSE_OTP_IN_RESPONSE",
        default=True,
    )
)


# ------------------------------------------------------------ logging -----
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "simple": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },

    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },

    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING" if not DEBUG else "INFO",
            "propagate": False,
        },

        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
