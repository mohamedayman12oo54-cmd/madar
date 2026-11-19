"""The audit log is append-only IN THE DATABASE, not just in Python.

`AuditLog.save()/delete()` already refuse changes, but that protects nothing against raw SQL, a future bug, a bulk
`_raw_delete`, or an operator's mistaken query. These row triggers make PostgreSQL itself refuse:

  * DELETE  — always refused;
  * UPDATE  — refused, with ONE exception: nulling `actor_id` (what `ON DELETE SET NULL` does when a team account is
              later removed; the readable `actor_label` snapshot stays), provided no other column changes.

TRUNCATE is deliberately not blocked (the test runner and `manage.py flush` use it); revoke that privilege from the
application's database role in production (see backend/SECURITY.md).
"""
from django.db import migrations

CREATE = """
CREATE OR REPLACE FUNCTION control_auditlog_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'control_auditlog is append-only: rows cannot be deleted';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.actor_label IS DISTINCT FROM OLD.actor_label
       OR NEW.action IS DISTINCT FROM OLD.action
       OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
       OR NEW.entity_id IS DISTINCT FROM OLD.entity_id
       OR NEW.entity_label IS DISTINCT FROM OLD.entity_label
       OR NEW.before IS DISTINCT FROM OLD.before
       OR NEW."after" IS DISTINCT FROM OLD."after"
       OR NEW.note IS DISTINCT FROM OLD.note
       OR NEW.ip_address IS DISTINCT FROM OLD.ip_address
       OR NEW.user_agent IS DISTINCT FROM OLD.user_agent
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR (NEW.actor_id IS DISTINCT FROM OLD.actor_id AND NEW.actor_id IS NOT NULL) THEN
        RAISE EXCEPTION 'control_auditlog is append-only: rows cannot be modified';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER control_auditlog_no_update BEFORE UPDATE ON control_auditlog
    FOR EACH ROW EXECUTE FUNCTION control_auditlog_guard();
CREATE TRIGGER control_auditlog_no_delete BEFORE DELETE ON control_auditlog
    FOR EACH ROW EXECUTE FUNCTION control_auditlog_guard();
"""

DROP = """
DROP TRIGGER IF EXISTS control_auditlog_no_update ON control_auditlog;
DROP TRIGGER IF EXISTS control_auditlog_no_delete ON control_auditlog;
DROP FUNCTION IF EXISTS control_auditlog_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("control", "0002_seed_defaults")]
    operations = [migrations.RunSQL(CREATE, DROP)]
