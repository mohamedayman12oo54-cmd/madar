"""
BILL-WU-003 — READ-ONLY INV-9 data check.

Run it against every database BEFORE environments.0002 (the OneToOne owner constraint) is applied.
It never writes. Output carries ids and counts only — no names, phones or e-mails (minors' data
posture). Exit status is non-zero when anything is non-compliant, so it can gate a deploy:

    python manage.py check_environment_cardinality && python manage.py migrate
"""
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count

from environments.models import Environment, EnvironmentMembership


def duplicate_owner_report():
    """[{owner_id, environments: [{id, created_at, volumes: {model_label: n}}]}] for owners with > 1."""
    owners = (
        Environment.objects.values("owner_id").annotate(n=Count("id")).filter(n__gt=1).order_by("owner_id")
    )
    tenant_models = [
        m for m in apps.get_models()
        if m is not Environment and any(
            f.name == "environment" and f.is_relation and f.related_model is Environment
            for f in m._meta.get_fields()
        )
    ]
    report = []
    for row in owners:
        envs = []
        for env in Environment.objects.filter(owner_id=row["owner_id"]).order_by("created_at", "id"):
            volumes = {}
            for model in tenant_models:
                count = model._base_manager.filter(environment_id=env.id).count()
                if count:
                    volumes[model._meta.label] = count
            envs.append({"id": env.id, "created_at": env.created_at.isoformat(), "volumes": volumes})
        report.append({"owner_id": row["owner_id"], "environments": envs})
    return report


def membership_incoherence():
    """BILL-RISK-27: owners lacking their owner membership, and owner memberships pointing at an
    Environment the user does not own."""
    owned = set(Environment.objects.values_list("id", "owner_id"))
    owner_memberships = set(
        EnvironmentMembership.objects.filter(role=EnvironmentMembership.Role.OWNER)
        .values_list("environment_id", "user_id")
    )
    return {
        "owner_without_membership": sorted(owned - owner_memberships),
        "membership_for_non_owner": sorted(owner_memberships - owned),
    }


class Command(BaseCommand):
    help = "Read-only: report teachers who own more than one Environment (INV-9) and owner/membership incoherence."

    def handle(self, *args, **options):
        db = connection.settings_dict
        self.stdout.write(f"database={db.get('NAME')} host={db.get('HOST') or 'local'}")
        duplicates = duplicate_owner_report()
        incoherence = membership_incoherence()
        self.stdout.write(f"owners_with_multiple_environments={len(duplicates)}")
        for owner in duplicates:
            self.stdout.write(f"  owner_id={owner['owner_id']}")
            for env in owner["environments"]:
                self.stdout.write(f"    environment_id={env['id']} created_at={env['created_at']} volumes={env['volumes']}")
        self.stdout.write(f"owner_without_membership={incoherence['owner_without_membership']}")
        self.stdout.write(f"membership_for_non_owner={incoherence['membership_for_non_owner']}")
        if duplicates or any(incoherence.values()):
            raise CommandError(
                "INV-9 check FAILED: do not apply environments.0002 to this database. "
                "Remediation needs an approved policy (BILL-DEC-01); never delete or merge automatically."
            )
        self.stdout.write(self.style.SUCCESS("INV-9 check passed: every teacher owns exactly one Environment."))
