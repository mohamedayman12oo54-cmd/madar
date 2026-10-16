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
    "knowledge",
    "parents",
    "billing",
    "studentarea",
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
# PostgreSQL is the ONLY supported database (SQLite support was removed).
# Billing (student-capacity limits, one invoice per cycle, webhook idempotency)
# relies on row locks and partial unique indexes. Credentials come from the
# environment only; there are no defaults for user/password/host.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("DB_NAME", "madar"),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", ""),
        "PORT": os.environ.get("DB_PORT", "5432"),
        # Reusing connections matters on PostgreSQL (each new connection forks
        # a backend process). 0 = close after every request (safe default for
        # local dev). CONN_HEALTH_CHECKS stops a pooled connection that the
        # server already dropped from surfacing as a request error.
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 0),
        "CONN_HEALTH_CHECKS": env_bool("DB_CONN_HEALTH_CHECKS", default=False),
    }
}

_db = DATABASES["default"]
if not (_db["USER"] and _db["PASSWORD"] and _db["HOST"]):
    raise ImproperlyConfigured(
        "PostgreSQL needs DB_USER, DB_PASSWORD and DB_HOST (see backend/POSTGRESQL.md)."
    )


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


# Test runs only: PBKDF2 is deliberately slow (that is its job in production);
# a fast hasher keeps the suite quick without touching real password security.
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


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
        # Guardians have no User row; they present a signed, read-only
        # session bound to one Enrollment (parents/auth.py).
        "parents.auth.ParentSessionAuthentication",
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
        # guardian code login: per IP, per guardian phone, per student code
        "guardian-login": "30/hour",
        "guardian-phone": "10/hour",
        "guardian-code": "10/hour",

        # --- per authenticated user ---
        "scan": "240/min",
        "video-upload": "20/hour",
        "student-add": "300/hour",
        "ai-submit": "30/hour",
        "broadcast": "20/hour",
        "password-change": "10/hour",
        "token-refresh": "300/hour",
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
    # Resumable video upload. Without these the browser's preflight fails and
    # the PATCH never reaches Django at all — which surfaces to the user as a
    # bare "unexpected error" with nothing in the server log.
    "upload-offset",
    "upload-length",
    "tus-resumable",
]

# The client must be able to READ the server's authoritative offset to resume.
CORS_EXPOSE_HEADERS = [
    "upload-offset",
    "upload-length",
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
# The resumable uploader PATCHes chunks up to MAX_CHUNK_BYTES (16 MiB), and
# Django raises RequestDataTooBig when `request.body` exceeds this limit — so
# it MUST stay above the chunk size or every real upload fails while small
# test chunks pass.
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 20 * 1024 * 1024)

# --- Private media (uploaded videos) ----------------------------------------
# NOT under STATIC_ROOT and never mapped to a public URL: every byte is served
# by an authenticated, authorisation-checked view (content.streaming). Uploads
# are large, so they stream to a temp file instead of being buffered in memory.
MEDIA_ROOT = os.environ.get("MEDIA_ROOT") or str(BASE_DIR / "private-media")
MEDIA_URL = None  # deliberately unset: there is no public media URL

VIDEO_MAX_BYTES = env_int("VIDEO_MAX_BYTES", 4 * 1024 * 1024 * 1024)  # 4 GB — uploads are chunked and resumable
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int("FILE_UPLOAD_MAX_MEMORY_SIZE", 2 * 1024 * 1024)
# Uploaded files must never be executable, and the private dir must not be
# world-readable.
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750

# How long a signed playback URL stays valid. Short enough that a copied link
# dies quickly; long enough to start a video on a slow connection.
# A playback URL must be self-authenticating (a <video> element cannot send an
# Authorization header), which makes it a BEARER credential: anyone holding it
# can stream until it expires. Hence a deliberately short life — long enough to
# start playing, short enough that a copied link is near-useless. The player
# re-requests a ticket when it needs one.
VIDEO_PLAYBACK_TTL_SECONDS = env_int("VIDEO_PLAYBACK_TTL_SECONDS", 120)
# Which content/providers.py implementation serves video. "local" = Madar
# stores and streams it itself (one rendition, no transcoding). A hosted
# provider would be added there, not by changing the domain.
VIDEO_PROVIDER = env_str("VIDEO_PROVIDER", "local")
# When behind nginx, set this to the internal location to hand streaming off
# to the web server (X-Accel-Redirect) instead of piping bytes through Django.
VIDEO_XACCEL_PREFIX = env_str("VIDEO_XACCEL_PREFIX", "")
# Quality ladder (360p/480p/720p/1080p) generated with ffmpeg after an upload.
# Needs `ffmpeg` + `ffprobe` on the server; if they are missing nothing breaks,
# students just see "تلقائي" (the original). Off while running the test suite.
VIDEO_TRANSCODE = env_bool("VIDEO_TRANSCODE", True) and "test" not in sys.argv
VIDEO_TRANSCODE_SYNC = False          # True = encode inside the request (tests only)
VIDEO_TRANSCODE_TIMEOUT = env_int("VIDEO_TRANSCODE_TIMEOUT", 3600)  # per rendition, seconds


# ------------------------------------------------- payment provider -------
# Which billing/providers.py implementation handles payments (BILL-WU-017).
# "fake" = a deterministic in-process fake with no network/credentials,
# default in DEBUG or under the test runner. "kashier" is the real adapter
# (BILL-WU-018, not implemented yet); its keys are mode-specific (test vs.
# live) and Kashier's own docs (reviewed 2026-10-15) say a key from one mode
# can't be used in the other.
PAYMENT_PROVIDER = env_str("PAYMENT_PROVIDER", "fake" if (DEBUG or "test" in sys.argv) else "kashier")
KASHIER_MODE = env_str("KASHIER_MODE", "test")
KASHIER_MERCHANT_ID = env_str("KASHIER_MERCHANT_ID", "")
KASHIER_PAYMENT_API_KEY_TEST = env_str("KASHIER_PAYMENT_API_KEY_TEST", "")
KASHIER_PAYMENT_API_KEY_LIVE = env_str("KASHIER_PAYMENT_API_KEY_LIVE", "")
KASHIER_SECRET_KEY_TEST = env_str("KASHIER_SECRET_KEY_TEST", "")
KASHIER_SECRET_KEY_LIVE = env_str("KASHIER_SECRET_KEY_LIVE", "")
KASHIER_API_BASE_TEST = env_str("KASHIER_API_BASE_TEST", "https://test-api.kashier.io")
KASHIER_API_BASE_LIVE = env_str("KASHIER_API_BASE_LIVE", "https://api.kashier.io")

if KASHIER_MODE not in ("test", "live"):
    raise ImproperlyConfigured("KASHIER_MODE must be 'test' or 'live'.")

# The fake provider must be impossible to select in production: it is a
# no-credentials stand-in, never a real payment path.
if not DEBUG and PAYMENT_PROVIDER == "fake":
    raise ImproperlyConfigured(
        "PAYMENT_PROVIDER=fake is not allowed when DJANGO_DEBUG is off. Configure "
        "PAYMENT_PROVIDER=kashier with the keys for the configured KASHIER_MODE."
    )

if not DEBUG and PAYMENT_PROVIDER == "kashier":
    _kashier_api_key = KASHIER_PAYMENT_API_KEY_TEST if KASHIER_MODE == "test" else KASHIER_PAYMENT_API_KEY_LIVE
    _kashier_secret = KASHIER_SECRET_KEY_TEST if KASHIER_MODE == "test" else KASHIER_SECRET_KEY_LIVE
    _kashier_api_key_name = "KASHIER_PAYMENT_API_KEY_TEST" if KASHIER_MODE == "test" else "KASHIER_PAYMENT_API_KEY_LIVE"
    _kashier_secret_name = "KASHIER_SECRET_KEY_TEST" if KASHIER_MODE == "test" else "KASHIER_SECRET_KEY_LIVE"
    _kashier_missing = [
        name for name, value in (
            ("KASHIER_MERCHANT_ID", KASHIER_MERCHANT_ID),
            (_kashier_api_key_name, _kashier_api_key),
            (_kashier_secret_name, _kashier_secret),
        )
        if not value
    ]
    if _kashier_missing:
        raise ImproperlyConfigured(
            f"PAYMENT_PROVIDER=kashier (KASHIER_MODE={KASHIER_MODE!r}) is missing: "
            f"{', '.join(_kashier_missing)}."
        )

# Live-mode kill switch for the renewal-charging worker (BILL-WU-025).
# Madar owns the billing schedule and initiates each cycle's charge
# itself, so this is the one setting that decides whether a real card is
# ever actually charged. Stays False until BILL-WU-026 (the 30-day
# compatibility gate) passes — this unit builds and verifies the
# capability against the fake provider only; it never flips this on.
BILLING_RENEWALS_LIVE_ENABLED = env_bool("BILLING_RENEWALS_LIVE_ENABLED", False)


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


# The OTP code is NEVER returned by the API outside `manage.py test` (the suite
# reads it from the `debug_otp` field). It is deliberately NOT controlled by an
# environment variable: anything in the response is readable by anyone in the
# browser's Network tab, which defeats sending the code to a phone/inbox, and a
# forgotten `.env` line must never be able to switch it on. In development read
# the code from the runserver terminal (console email) or your real inbox.
EXPOSE_OTP_IN_RESPONSE = "test" in sys.argv


# ------------------------------------------------- OTP delivery (SMS/email) -
# Email goes through Django's normal email machinery. In DEBUG the default is
# the console backend (the message is printed by runserver); outside DEBUG it
# is SMTP and EMAIL_HOST / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD must be set
# (Gmail SMTP works with an app password: smtp.gmail.com:587, TLS).
EMAIL_BACKEND = env_str(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = env_str("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "Madar <no-reply@madar.local>")

# SMS has no built-in provider. Point this at a class with
# `send(phone, message)` (see accounts/delivery.py) once an SMS account
# exists. The default only logs, and outside DEBUG it refuses to pretend a
# message was sent.
OTP_SMS_BACKEND = env_str("OTP_SMS_BACKEND", "accounts.delivery.ConsoleSMSBackend")
# Fixed at startup (not read from settings.DEBUG at runtime, which Django's
# test runner forces to False): may the console SMS stand-in count as "sent"?
OTP_SMS_CONSOLE_ALLOWED = DEBUG


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
