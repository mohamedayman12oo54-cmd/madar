"""Test helpers. Throttle counters live in the cache, which persists across
tests inside one process — clear it before every test so a rate-limit test
can never make an unrelated test fail (and vice-versa)."""
from django.core.cache import cache
from django.test import TestCase as DjangoTestCase


class TestCase(DjangoTestCase):
    def _pre_setup(self):
        cache.clear()
        super()._pre_setup()
