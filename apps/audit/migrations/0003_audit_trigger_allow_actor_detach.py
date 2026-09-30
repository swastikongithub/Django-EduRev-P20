from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION audit_log_is_append_only() RETURNS trigger AS $$
BEGIN
    -- The only permitted change: ON DELETE SET NULL detaching a deleted user (DPDP erasure).
    -- The action, target, before/after and timestamp stay intact; actor_label keeps the name.
    IF TG_OP = 'UPDATE' AND NEW.actor_id IS NULL
       AND (to_jsonb(OLD) - 'actor_id') = (to_jsonb(NEW) - 'actor_id') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'audit_auditlog is append-only (% rejected)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

-- TRUNCATE is an owner-only operation; the application role is not the owner in production.
-- Dropping this trigger lets the test runner reset the database between transactional tests.
DROP TRIGGER IF EXISTS audit_auditlog_no_truncate ON audit_auditlog;
"""

REVERSE = """
CREATE TRIGGER audit_auditlog_no_truncate
    BEFORE TRUNCATE ON audit_auditlog
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_is_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0002_immutable_audit_log")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
