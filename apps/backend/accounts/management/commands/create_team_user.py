import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.validators import password_meets_rules

User = get_user_model()


class Command(BaseCommand):
    """There is no public signup screen for the 'team' role (content /
    knowledge management staff) — accounts are provisioned directly by
    whoever runs the backend, via this command or the Django admin."""

    help = "Create a 'team' role account (content/knowledge management)."

    def add_arguments(self, parser):
        parser.add_argument("identifier", help="Login identifier shown on the team login screen, e.g. team@madar")
        parser.add_argument("--name", default="", help="Display name")

    def handle(self, *args, **options):
        identifier = options["identifier"].strip()
        if User.objects.filter(username__iexact=identifier).exists():
            raise CommandError(f"'{identifier}' already exists.")

        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise CommandError("Passwords do not match.")
        if not password_meets_rules(password):
            raise CommandError("Password does not meet the required rules (8+ chars, upper, lower, digit, symbol).")

        User.objects.create_user(
            username=identifier,
            role=User.Role.TEAM,
            name=options["name"] or identifier,
            password=password,
            is_active=True,
            is_verified=True,
        )
        self.stdout.write(self.style.SUCCESS(f"Team account '{identifier}' created."))
