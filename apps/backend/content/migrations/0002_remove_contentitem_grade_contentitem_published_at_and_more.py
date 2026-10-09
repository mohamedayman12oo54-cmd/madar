from django.db import migrations, models


def copy_grade_to_targets(apps, schema_editor):
    """Existing items were visible to their grade's students: keep that by
    turning the old single `grade` into a grade TARGET and marking the item
    published (no notification is fired for pre-existing content)."""
    ContentItem = apps.get_model("content", "ContentItem")
    for item in ContentItem.objects.exclude(grade_id=None).iterator():
        item.target_grades.add(item.grade_id)
        item.published_at = item.created_at
        item.save(update_fields=["published_at"])


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0002_enrollment_teacher_scoped_identity_and_groups'),
        ('content', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='contentitem',
            name='published_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='contentitem',
            name='target_enrollments',
            field=models.ManyToManyField(blank=True, related_name='content_items', to='academics.enrollment'),
        ),
        migrations.AddField(
            model_name='contentitem',
            name='target_grades',
            field=models.ManyToManyField(blank=True, related_name='+', to='academics.grade'),
        ),
        migrations.AddField(
            model_name='contentitem',
            name='target_groups',
            field=models.ManyToManyField(blank=True, related_name='content_items', to='academics.group'),
        ),
        migrations.RunPython(copy_grade_to_targets, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='contentitem',
            name='grade',
        ),
        migrations.AlterField(
            model_name='contentitem',
            name='target_grades',
            field=models.ManyToManyField(blank=True, related_name='content_items', to='academics.grade'),
        ),
    ]
