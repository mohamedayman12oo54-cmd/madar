"""Give every Enrollment an opaque QR badge handle.

Adding a UNIQUE column to a populated table needs three steps: add it
nullable, fill each row with its OWN random value, then enforce uniqueness.
A single `AddField(unique=True, default=...)` would write the SAME default
into every existing row and fail the unique constraint.
"""
from django.db import migrations, models

import academics.models


def issue_tokens(apps, schema_editor):
    Enrollment = apps.get_model("academics", "Enrollment")
    for pk in Enrollment.objects.filter(qr_token__isnull=True).values_list("pk", flat=True).iterator():
        Enrollment.objects.filter(pk=pk).update(qr_token=academics.models.new_qr_token())


class Migration(migrations.Migration):

    dependencies = [("academics", "0002_enrollment_teacher_scoped_identity_and_groups")]

    operations = [
        migrations.AddField(
            model_name="enrollment",
            name="qr_token",
            field=models.CharField(max_length=43, null=True, editable=False),
        ),
        migrations.RunPython(issue_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="enrollment",
            name="qr_token",
            field=models.CharField(
                max_length=43, unique=True, editable=False,
                default=academics.models.new_qr_token,
            ),
        ),
    ]
