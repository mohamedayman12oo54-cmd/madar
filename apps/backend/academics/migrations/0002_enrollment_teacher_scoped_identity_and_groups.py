from django.db import migrations, models


def forwards(apps, schema_editor):
    Enrollment = apps.get_model("academics", "Enrollment")
    for e in Enrollment.objects.select_related("student").iterator():
        e.student_name = e.student.name or ""
        e.save(update_fields=["student_name"])
        if e.group_id:
            e.groups.add(e.group_id)


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0001_initial"),
    ]

    operations = [
        migrations.AddField(model_name="enrollment", name="student_name", field=models.CharField(blank=True, max_length=150)),
        migrations.AddField(model_name="enrollment", name="parent_name", field=models.CharField(blank=True, max_length=150)),
        migrations.AddField(model_name="enrollment", name="parent_phone", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(
            model_name="enrollment",
            name="groups",
            field=models.ManyToManyField(blank=True, related_name="member_enrollments", to="academics.group"),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.RemoveField(model_name="enrollment", name="group"),
    ]
