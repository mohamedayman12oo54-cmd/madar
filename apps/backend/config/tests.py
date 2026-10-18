"""
Phase 0 / S8 — production configuration guard rails and safe error output.

Settings are evaluated at import time, so each scenario runs in a fresh
subprocess with an explicit environment. Every variable the settings read is
set explicitly (empty string = "unset") so a developer's local `.env` file
can never change the result: python-dotenv never overrides variables that are
already present in the environment.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from accounts.testing import TestCase

BASE_DIR = Path(__file__).resolve().parent.parent
GOOD_KEY = "k8Xp2vQ7mZr4TnYw9LbC3sHd6FgJ1aEu5NoRt0PiVxWq8MzA2ByKc7DhSl4GeUf"

SETTINGS_VARS = [
    "DJANGO_SECRET_KEY", "DJANGO_DEBUG", "DJANGO_ALLOWED_HOSTS", "DJANGO_TIME_ZONE",
    "CORS_ALLOWED_ORIGINS", "DJANGO_CSRF_TRUSTED_ORIGINS", "DJANGO_NUM_PROXIES",
    "DJANGO_BEHIND_TLS_PROXY", "DJANGO_CACHE_BACKEND", "DJANGO_SECURE_SSL_REDIRECT",
    "DJANGO_HSTS_SECONDS", "DJANGO_HSTS_INCLUDE_SUBDOMAINS", "DJANGO_HSTS_PRELOAD",
    "EXPOSE_OTP_IN_RESPONSE", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT",
    # BILL-WU-017: PAYMENT_PROVIDER defaults to "kashier" (not "fake") once
    # DJANGO_DEBUG is off, so a "valid production config" now needs these
    # too — blanked here like every other settings-read variable.
    "PAYMENT_PROVIDER", "KASHIER_MODE", "KASHIER_MERCHANT_ID",
    "KASHIER_PAYMENT_API_KEY_TEST", "KASHIER_PAYMENT_API_KEY_LIVE",
    "KASHIER_SECRET_KEY_TEST", "KASHIER_SECRET_KEY_LIVE",
]

PROD = {
    "DJANGO_SECRET_KEY": GOOD_KEY,
    "DJANGO_DEBUG": "False",
    "DJANGO_ALLOWED_HOSTS": "api.example.com",
    "CORS_ALLOWED_ORIGINS": "https://app.example.com",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.example.com",
    # BILL-WU-017: a minimal valid Kashier config so this fixture still
    # represents "a complete, valid production config" after that unit
    # added its own mandatory settings.
    "KASHIER_MERCHANT_ID": "m", "KASHIER_PAYMENT_API_KEY_TEST": "k", "KASHIER_SECRET_KEY_TEST": "s",
}

DUMP = """
import json, django
from django.conf import settings as s
print(json.dumps({
  "DEBUG": s.DEBUG, "HOSTS": s.ALLOWED_HOSTS, "SSL_REDIRECT": s.SECURE_SSL_REDIRECT,
  "SESSION_SECURE": s.SESSION_COOKIE_SECURE, "CSRF_SECURE": s.CSRF_COOKIE_SECURE,  
  "CSRF_HTTPONLY": s.CSRF_COOKIE_HTTPONLY, "HSTS": s.SECURE_HSTS_SECONDS,
  "PROXY_HEADER": s.SECURE_PROXY_SSL_HEADER, "NUM_PROXIES": s.REST_FRAMEWORK["NUM_PROXIES"],
  "CACHE": s.CACHES["default"]["BACKEND"], "EXPOSE_OTP": s.EXPOSE_OTP_IN_RESPONSE,
  "XFO": s.X_FRAME_OPTIONS, "NOSNIFF": s.SECURE_CONTENT_TYPE_NOSNIFF,
  "CORS": s.CORS_ALLOWED_ORIGINS, "THROTTLE_CLASSES": list(s.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]),
}))
"""


def run_python(code, overrides, argv=None):
    env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "HOME") if k in os.environ}
    env.update({name: "" for name in SETTINGS_VARS})
    # PostgreSQL is mandatory; settings refuse to load without credentials.
    # Dummy values are enough because these scenarios never open a connection.
    env.update({"DB_USER": "u", "DB_PASSWORD": "p", "DB_HOST": "localhost"})
    env.update(overrides)
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    env["PYTHONPATH"] = str(BASE_DIR)
    return subprocess.run([sys.executable, "-c", code] if argv is None else argv,
                          cwd=BASE_DIR, env=env, capture_output=True, text=True, timeout=120)


def load(overrides):
    r = run_python(DUMP, overrides)
    return r, (json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else None)


class ProductionGuardRailTests(SimpleTestCase):
    def assertRefuses(self, overrides, fragment):
        r, _ = load({**PROD, **overrides})
        self.assertNotEqual(r.returncode, 0, "settings should have refused to load")
        self.assertIn("ImproperlyConfigured", r.stderr)
        self.assertIn(fragment, r.stderr)

    # --- SECRET_KEY --------------------------------------------------------
    def test_missing_secret_key_refused(self):
        self.assertRefuses({"DJANGO_SECRET_KEY": ""}, "DJANGO_SECRET_KEY")

    def test_placeholder_from_env_example_refused(self):
        """regression: the old guard only rejected one exact fallback string, so
        the '.env.example' placeholder booted fine in production."""
        self.assertRefuses({"DJANGO_SECRET_KEY": "change-me-to-a-long-random-value"}, "DJANGO_SECRET_KEY")

    def test_dev_fallback_key_refused(self):
        self.assertRefuses({"DJANGO_SECRET_KEY": "insecure-dev-only-key-do-not-use-in-production"}, "DJANGO_SECRET_KEY")

    def test_short_or_low_entropy_key_refused(self):
        self.assertRefuses({"DJANGO_SECRET_KEY": "a1b2c3d4e5"}, "DJANGO_SECRET_KEY")
        self.assertRefuses({"DJANGO_SECRET_KEY": "x" * 60}, "DJANGO_SECRET_KEY")

    # --- DATABASE ----------------------------------------------------------
    def test_missing_postgres_credentials_refused(self):
        """PostgreSQL is the only database: no credentials, no boot."""
        for missing in ("DB_USER", "DB_PASSWORD", "DB_HOST"):
            with self.subTest(missing=missing):
                self.assertRefuses({missing: ""}, "DB_USER, DB_PASSWORD and DB_HOST")

    def test_database_engine_is_always_postgresql(self):
        # A leftover DB_ENGINE in someone's .env must no longer select SQLite.
        r = run_python("from django.conf import settings as s; print(s.DATABASES['default']['ENGINE'])",
                       {**PROD, "DB_ENGINE": "django.db.backends.sqlite3"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "django.db.backends.postgresql")

    # --- ALLOWED_HOSTS -----------------------------------------------------
    def test_empty_allowed_hosts_refused_in_production(self):
        """regression: production silently defaulted to localhost."""
        self.assertRefuses({"DJANGO_ALLOWED_HOSTS": ""}, "DJANGO_ALLOWED_HOSTS")

    def test_wildcard_allowed_hosts_refused(self):
        self.assertRefuses({"DJANGO_ALLOWED_HOSTS": "*"}, "DJANGO_ALLOWED_HOSTS")
        self.assertRefuses({"DJANGO_ALLOWED_HOSTS": "api.example.com,*"}, "DJANGO_ALLOWED_HOSTS")

    # --- CORS / CSRF -------------------------------------------------------
    def test_non_https_or_wildcard_cors_refused(self):
        self.assertRefuses({"CORS_ALLOWED_ORIGINS": "http://app.example.com"}, "CORS_ALLOWED_ORIGINS")
        self.assertRefuses({"CORS_ALLOWED_ORIGINS": "*"}, "CORS_ALLOWED_ORIGINS")
        self.assertRefuses({"CORS_ALLOWED_ORIGINS": "https://ok.example.com,http://bad.example.com"}, "CORS_ALLOWED_ORIGINS")

    def test_non_https_csrf_origin_refused(self):
        self.assertRefuses({"DJANGO_CSRF_TRUSTED_ORIGINS": "http://app.example.com"}, "DJANGO_CSRF_TRUSTED_ORIGINS")

    def test_bad_integer_env_refused(self):
        self.assertRefuses({"DJANGO_NUM_PROXIES": "one"}, "DJANGO_NUM_PROXIES")

    # --- valid production config ------------------------------------------
    def test_valid_production_config_is_locked_down(self):
        r, s = load(PROD)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(s["DEBUG"])
        self.assertEqual(s["HOSTS"], ["api.example.com"])
        self.assertTrue(s["SSL_REDIRECT"])
        self.assertTrue(s["SESSION_SECURE"] and s["CSRF_SECURE"] and s["CSRF_HTTPONLY"])
        self.assertGreater(s["HSTS"], 0)
        self.assertEqual(s["XFO"], "DENY")
        self.assertTrue(s["NOSNIFF"])
        self.assertEqual(s["CORS"], ["https://app.example.com"])

    def test_production_uses_shared_db_cache_and_trusts_no_proxy_by_default(self):
        _, s = load(PROD)
        self.assertTrue(s["CACHE"].endswith("DatabaseCache"), s["CACHE"])
        self.assertEqual(s["NUM_PROXIES"], 0)
        self.assertIsNone(s["PROXY_HEADER"])

    def test_otp_is_never_exposed_in_production_even_if_env_asks(self):
        _, s = load({**PROD, "EXPOSE_OTP_IN_RESPONSE": "True"})
        self.assertFalse(s["EXPOSE_OTP"])

    def test_blank_env_values_fall_back_to_the_safe_default(self):
        """`DJANGO_SECURE_SSL_REDIRECT=` (blank line in .env) must not silently
        turn the protection off."""
        r, s = load({**PROD, "DJANGO_SECURE_SSL_REDIRECT": "  ", "DJANGO_CACHE_BACKEND": "", "DJANGO_HSTS_SECONDS": ""})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(s["SSL_REDIRECT"])
        self.assertGreater(s["HSTS"], 0)
        self.assertTrue(s["CACHE"].endswith("DatabaseCache"))

    def test_proxy_settings_are_opt_in(self):
        _, s = load({**PROD, "DJANGO_BEHIND_TLS_PROXY": "True", "DJANGO_NUM_PROXIES": "1"})
        self.assertEqual(s["PROXY_HEADER"], ["HTTP_X_FORWARDED_PROTO", "https"])
        self.assertEqual(s["NUM_PROXIES"], 1)

    def test_dev_mode_still_works_without_any_env(self):
        r, s = load({"DJANGO_DEBUG": "True"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(s["DEBUG"])
        self.assertFalse(s["SSL_REDIRECT"])  # http://localhost dev keeps working
        self.assertIn("http://localhost:5173", s["CORS"])
        self.assertTrue(s["CACHE"].endswith("LocMemCache"))

    def test_no_default_throttles_but_rates_are_defined_for_every_scope(self):
        _, s = load(PROD)
        self.assertEqual(s["THROTTLE_CLASSES"], [])
        r = run_python(
            "import django; django.setup()\n"
            "from django.conf import settings as s\n"
            "import accounts.throttles as t, inspect\n"
            "from rest_framework.throttling import SimpleRateThrottle as B\n"
            "scopes={c.scope for _,c in inspect.getmembers(t, inspect.isclass) if issubclass(c,B) and getattr(c,'scope',None)}\n"
            "missing=scopes-set(s.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'])\n"
            "print('MISSING', sorted(missing)); print('N', len(scopes))\n",
            PROD,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("MISSING []", r.stdout)

    def test_django_deploy_check_is_clean_for_a_valid_production_config(self):
        r = run_python("", PROD, argv=[sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class SafeErrorOutputTests(TestCase):
    """S8 — no tracebacks, paths, SQL or exception text reach API clients."""

    def test_unknown_url_returns_json_404(self):
        r = APIClient().get("/api/v1/does-not-exist/")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r["Content-Type"], "application/json")
        self.assertEqual(r.json()["code"], "not_found")

    def test_unhandled_exception_returns_generic_json_500(self):
        from accounts.models import User
        u = User.objects.create_user(role="teacher", name="T", email="t@example.com", phone="201001111111",
                                     password="Str0ng!Pass", is_active=True)
        c = APIClient()
        c.raise_request_exception = False
        tok = c.post("/api/v1/auth/teacher/login/", {"identifier": "t@example.com", "password": "Str0ng!Pass"}).data["access"]
        c.credentials(HTTP_AUTHORIZATION="Bearer " + tok)
        secret = "SECRET_INTERNAL /srv/madar/accounts/models.py SELECT * FROM accounts_user"
        with mock.patch("accounts.views.UserPublicSerializer", side_effect=RuntimeError(secret)):
            r = c.get("/api/v1/auth/me/")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r["Content-Type"], "application/json")
        body = r.content.decode()
        for leak in ("SECRET_INTERNAL", "/srv/madar", "SELECT", "Traceback", "RuntimeError"):
            self.assertNotIn(leak, body)
        self.assertEqual(r.json()["code"], "server_error")

    def test_validation_errors_do_not_echo_internals(self):
        r = APIClient().post("/api/v1/auth/teacher/login/", {"identifier": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("Traceback", r.content.decode())

    def test_protected_endpoint_requires_authentication(self):
        self.assertEqual(APIClient().get("/api/v1/auth/me/").status_code, 401)
        self.assertEqual(APIClient().get("/api/v1/environments/teacher/").status_code, 401)
        self.assertEqual(APIClient().get("/api/v1/environments/student/").status_code, 401)
