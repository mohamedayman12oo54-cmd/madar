"""BILL-WU-038..042 scope guards: things this plan deliberately does NOT build must stay unbuildable."""
from django.contrib import admin
from django.test import SimpleTestCase

from billing import models as billing_models


class OutOfScopeGuardTests(SimpleTestCase):
    def test_no_billing_model_is_editable_through_the_django_admin(self):
        """BILL-WU-042: plan prices are changed by data migration only. Registering them in the admin
        would let anyone silently change the amount of every future renewal."""
        registered = [m.__name__ for m in vars(billing_models).values()
                      if isinstance(m, type) and hasattr(m, "_meta") and m.__module__ == "billing.models"
                      and admin.site.is_registered(m)]
        self.assertEqual(registered, [])

    def test_no_refund_or_proration_or_tax_fields_exist(self):
        names = {f.name.lower() for model in vars(billing_models).values()
                 if isinstance(model, type) and hasattr(model, "_meta") and not model._meta.abstract
                 for f in model._meta.get_fields()}
        for forbidden in ("refund", "refunded", "proration", "prorated", "tax", "vat", "invoice_number", "pan", "cvv", "cvc"):
            self.assertNotIn(forbidden, names)
