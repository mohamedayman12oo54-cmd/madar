"""Development helper: explains why a login identifier does not match any
account, WITHOUT ever touching or printing passwords.

    python manage.py diagnose_login 01065692895

It is refused when DEBUG is off, because telling a caller which accounts
exist and how they are stored is exactly the oracle the API deliberately
never provides."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from accounts.models import User
from accounts.phones import PhoneError, canonical_phone, digits_only


class Command(BaseCommand):
    help = "Dev only: show how an identifier (phone or email) maps to stored accounts."

    def add_arguments(self, parser):
        parser.add_argument("identifier")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("diagnose_login is disabled when DEBUG is False.")
        ident = options["identifier"].strip()
        out = self.stdout.write
        if "@" in ident:
            users = User.objects.filter(email__iexact=ident)
            out(f"Looked up as e-mail -> {users.count()} account(s)")
        else:
            try:
                canonical = canonical_phone(ident, default_country="EG")
                out(f"Canonical form the login looks for: {canonical}")
            except PhoneError as exc:
                canonical = None
                out(self.style.ERROR(f"Not a valid mobile number: {exc.message_ar}"))
            national = digits_only(ident).lstrip("0")[-10:]
            q = Q(phone=canonical) if canonical else Q(pk__in=[])
            if national:
                q |= Q(phone__endswith=national)
            users = User.objects.filter(q)
        if not users:
            out(self.style.WARNING("No matching account at all -> the account does not exist (sign up, or run seed_demo)."))
            return
        for u in users:
            exact = canonical is not None and "@" not in ident and u.phone == canonical
            out(f"  #{u.id} role={u.role} active={u.is_active} verified={u.is_verified} stored_phone={u.phone!r} email={u.email!r}"
                f"  -> {'MATCHES the login lookup' if exact or '@' in ident else 'stored in another format (run: python manage.py migrate)'}")
            if not u.is_active:
                out(self.style.WARNING("     account is inactive: login refuses it (teacher signup not completed, or student unclaimed)."))
