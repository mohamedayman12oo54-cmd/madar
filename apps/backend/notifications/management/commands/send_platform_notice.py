"""Platform → people notice ("from us"): a push to every subscribed device of the chosen audience.

    python manage.py send_platform_notice --audience teachers --title "تحديث جديد" --body "..." --url /app
    python manage.py send_platform_notice --audience students --title ... --body ...
    python manage.py send_platform_notice --audience all --user-id 12 ...   (one specific account)

It is push-only: it does not create inbox rows (those belong to a teacher's environment)."""
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from notifications import webpush
from notifications.models import PushSubscription


class Command(BaseCommand):
    help = "Send a platform notice by Web Push."

    def add_arguments(self, p):
        p.add_argument("--audience", choices=["teachers", "students", "all"], default="all")
        p.add_argument("--user-id", type=int)
        p.add_argument("--title", required=True)
        p.add_argument("--body", default="")
        p.add_argument("--url", default="/")

    def handle(self, *a, **o):
        if not webpush.enabled():
            raise CommandError("VAPID keys are not configured (run generate_vapid_keys).")
        ids = PushSubscription.objects.values_list("user_id", flat=True).distinct()
        users = User.objects.filter(pk__in=ids)
        if o["user_id"]:
            users = users.filter(pk=o["user_id"])
        elif o["audience"] != "all":
            users = users.filter(role=User.Role.TEACHER if o["audience"] == "teachers" else User.Role.STUDENT)
        total = {"sent": 0, "failed": 0, "removed": 0}
        for uid in users.values_list("pk", flat=True):
            for k, v in webpush.send_to_user(uid, o["title"], o["body"], o["url"], tag="platform").items():
                total[k] += v
        self.stdout.write(self.style.SUCCESS(f"devices: {total['sent']} sent, {total['failed']} failed, {total['removed']} removed"))
