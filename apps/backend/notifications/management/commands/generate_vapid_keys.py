"""Prints a fresh VAPID key pair as .env lines. Run ONCE per deployment and keep the private key secret;
changing it later invalidates every existing subscription (users would have to re-enable notifications)."""
import base64

from cryptography.hazmat.primitives import serialization
from django.core.management.base import BaseCommand
from py_vapid import Vapid


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "Generate VAPID keys for Web Push."

    def handle(self, *args, **options):
        v = Vapid()
        v.generate_keys()
        public = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        private = v.private_key.private_numbers().private_value.to_bytes(32, "big")
        self.stdout.write("# add to backend/.env\n")
        self.stdout.write(f"VAPID_PUBLIC_KEY={_b64(public)}\n")
        self.stdout.write(f"VAPID_PRIVATE_KEY={_b64(private)}\n")
        self.stdout.write("VAPID_CONTACT=mailto:you@example.com\n")
