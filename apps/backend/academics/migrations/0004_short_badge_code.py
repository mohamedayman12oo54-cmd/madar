"""Reissue badge handles as short, human-readable 6-character codes.

Existing rows hold 43-character tokens that no longer fit the column, so every
badge is reissued. That intentionally invalidates previously printed badges —
the same thing a rotation does — and there is no way to keep them, since the
whole point of the change is the shorter format.
"""
from django.db import migrations, models

import academics.models


def reissue(apps, schema_editor):
    Enrollment = apps.get_model("academics", "Enrollment")
    taken = set()
    for pk in Enrollment.objects.values_list("pk", flat=True).iterator():
        for _ in range(20):
            code = academics.models.new_qr_token()
            if code not in taken:
                taken.add(code)
                Enrollment.objects.filter(pk=pk).update(qr_token=code)
                break


class Migration(migrations.Migration):

    dependencies = [("academics", "0003_enrollment_qr_token")]

    operations = [
        # Drop uniqueness first so the rewrite cannot trip over itself, then
        # shorten, fill, and restore the constraint.
        migrations.AlterField(
            model_name="enrollment",
            name="qr_token",
            field=models.CharField(max_length=43, null=True, editable=False),
        ),
        migrations.RunPython(reissue, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="enrollment",
            name="qr_token",
            field=models.CharField(
                max_length=6, unique=True, editable=False,
                default=academics.models.new_qr_token,
            ),
        ),
    ]
