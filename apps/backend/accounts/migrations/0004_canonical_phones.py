"""Normalise every stored phone to the canonical form (dial code + national
number, digits only, e.g. 201065692895).

Before country-aware validation, accounts were saved exactly as typed
("01065692895", "1065692895", ...), so logging in with the same number now
looked it up in a different form and failed. This brings existing rows (all
roles: teachers, students, team) in line. Rows that cannot be converted
safely are LEFT UNTOUCHED and listed, never guessed at or deleted:

  * a number that is not a valid mobile number of a supported country
  * a number whose canonical form already belongs to another account
"""
from django.db import migrations

from accounts.phones import try_canonical_phone


def canonicalize_phones(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    skipped = []
    changed = 0
    taken = set(User.objects.exclude(phone="").values_list("phone", flat=True))
    for user in User.objects.exclude(phone="").order_by("id"):
        canonical = try_canonical_phone(user.phone, default_country="EG")
        if canonical is None:
            skipped.append((user.id, user.phone, "not a valid mobile number for a supported country"))
            continue
        if canonical == user.phone:
            continue
        if canonical in taken:
            skipped.append((user.id, user.phone, f"{canonical} already belongs to another account"))
            continue
        taken.discard(user.phone)
        taken.add(canonical)
        User.objects.filter(pk=user.pk).update(phone=canonical)
        changed += 1
    if changed or skipped:
        print(f"\n  phones normalised: {changed}; left unchanged: {len(skipped)}")
        for uid, phone, why in skipped:
            print(f"    user #{uid} phone={phone!r}: {why}")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_user_session_version"),
    ]

    operations = [
        migrations.RunPython(canonicalize_phones, migrations.RunPython.noop),
    ]
