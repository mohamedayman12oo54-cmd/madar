"""
BILL-WU-017 — AC-BILL-017-3/4: payment-provider production guard rails.

Reuses `config.tests`'s existing subprocess settings harness (`run_python`,
`PROD`) rather than duplicating it — settings are evaluated at import time,
so each scenario needs its own fresh subprocess with an explicit
environment, exactly like the other production guard-rail tests there.
"""
from django.test import SimpleTestCase

from config.tests import PROD, run_python

# Settings are evaluated lazily on first access, so the probe code MUST
# actually touch `django.conf.settings` — `print('ok')` alone would exit 0
# unconditionally without ever importing `config.settings`, silently
# proving nothing. `django.setup()` forces that evaluation the same way
# `manage.py`/the WSGI app does.
_PROBE_CODE = "import django; django.setup(); print('ok')"


class PaymentProviderGuardRailTests(SimpleTestCase):
    def assertRefuses(self, overrides, fragment):
        r = run_python(_PROBE_CODE, {**PROD, **overrides})
        self.assertNotEqual(r.returncode, 0, "settings should have refused to load")
        self.assertIn("ImproperlyConfigured", r.stderr)
        self.assertIn(fragment, r.stderr)

    def assertBoots(self, overrides):
        r = run_python(_PROBE_CODE, {**PROD, **overrides})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ok", r.stdout)

    # --- AC-BILL-017-3: fake provider never allowed in production ---------
    def test_fake_provider_refused_in_production(self):
        self.assertRefuses({"PAYMENT_PROVIDER": "fake"}, "PAYMENT_PROVIDER=fake")

    def test_fake_provider_allowed_in_debug(self):
        # DEBUG relaxes several other guards too (ALLOWED_HOSTS, HTTPS-only
        # origins); only PAYMENT_PROVIDER/KASHIER_MODE are under test here.
        self.assertBoots({"DJANGO_DEBUG": "True", "PAYMENT_PROVIDER": "fake"})

    # --- AC-BILL-017-4: kashier mode keys required in production ----------
    def test_kashier_missing_merchant_id_refused(self):
        # PROD now supplies a default KASHIER_MERCHANT_ID (so it still
        # represents "a complete valid production config" after this unit
        # added the requirement) — blank it explicitly to test its absence.
        self.assertRefuses(
            {
                "PAYMENT_PROVIDER": "kashier", "KASHIER_MODE": "test", "KASHIER_MERCHANT_ID": "",
                "KASHIER_PAYMENT_API_KEY_TEST": "x", "KASHIER_SECRET_KEY_TEST": "y",
            },
            "KASHIER_MERCHANT_ID",
        )

    def test_kashier_missing_test_mode_api_key_refused(self):
        self.assertRefuses(
            {
                "PAYMENT_PROVIDER": "kashier", "KASHIER_MODE": "test",
                "KASHIER_MERCHANT_ID": "m", "KASHIER_PAYMENT_API_KEY_TEST": "", "KASHIER_SECRET_KEY_TEST": "y",
            },
            "KASHIER_PAYMENT_API_KEY_TEST",
        )

    def test_kashier_live_mode_checks_live_keys_not_test_keys(self):
        # Test-mode keys present but irrelevant; live keys missing — must
        # still refuse, and must name the LIVE variable, not the test one.
        self.assertRefuses(
            {
                "PAYMENT_PROVIDER": "kashier", "KASHIER_MODE": "live",
                "KASHIER_MERCHANT_ID": "m",
                "KASHIER_PAYMENT_API_KEY_TEST": "x", "KASHIER_SECRET_KEY_TEST": "y",
            },
            "KASHIER_PAYMENT_API_KEY_LIVE",
        )

    def test_kashier_fully_configured_for_test_mode_boots(self):
        self.assertBoots(
            {
                "PAYMENT_PROVIDER": "kashier", "KASHIER_MODE": "test",
                "KASHIER_MERCHANT_ID": "m", "KASHIER_PAYMENT_API_KEY_TEST": "k",
                "KASHIER_SECRET_KEY_TEST": "s",
            }
        )

    def test_invalid_kashier_mode_refused(self):
        self.assertRefuses({"KASHIER_MODE": "sandbox"}, "KASHIER_MODE")


class EnvExampleListsNamesOnlyTests(SimpleTestCase):
    """AC-BILL-017-5: `.env.example` lists the new variable names with no
    real value, and no secret-shaped value appears in the repo."""

    EXPECTED_NAMES = (
        "PAYMENT_PROVIDER", "KASHIER_MODE", "KASHIER_MERCHANT_ID",
        "KASHIER_PAYMENT_API_KEY_TEST", "KASHIER_PAYMENT_API_KEY_LIVE",
        "KASHIER_SECRET_KEY_TEST", "KASHIER_SECRET_KEY_LIVE",
        "KASHIER_API_BASE_TEST", "KASHIER_API_BASE_LIVE",
    )

    def test_every_new_name_is_listed_with_no_secret_value(self):
        from config.settings import BASE_DIR

        content = (BASE_DIR / ".env.example").read_text(encoding="utf-8")
        for name in self.EXPECTED_NAMES:
            self.assertIn(name, content, f"{name} is missing from .env.example")

        # The two key/secret pairs must carry no value at all (just the bare
        # name) — the "=" line has nothing after it.
        for name in (
            "KASHIER_MERCHANT_ID", "KASHIER_PAYMENT_API_KEY_TEST",
            "KASHIER_PAYMENT_API_KEY_LIVE", "KASHIER_SECRET_KEY_TEST", "KASHIER_SECRET_KEY_LIVE",
        ):
            for line in content.splitlines():
                stripped = line.strip().lstrip("#").strip()
                if stripped.startswith(f"{name}="):
                    self.assertEqual(stripped, f"{name}=", f"{name} must have no value in .env.example")
