from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION audit_log_is_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditlog is append-only (% rejected)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_auditlog_no_update
    BEFORE UPDATE OR DELETE ON audit_auditlog
    FOR EACH ROW EXECUTE FUNCTION audit_log_is_append_only();

CREATE TRIGGER audit_auditlog_no_truncate
    BEFORE TRUNCATE ON audit_auditlog
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_is_append_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS audit_auditlog_no_update ON audit_auditlog;
DROP TRIGGER IF EXISTS audit_auditlog_no_truncate ON audit_auditlog;
DROP FUNCTION IF EXISTS audit_log_is_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
