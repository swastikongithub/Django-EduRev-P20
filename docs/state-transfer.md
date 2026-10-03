# Moving an installation's state (local → production)

A one-time, deliberate copy of a fully built installation (catalogue, rules, timetable, bookings and
everything that decides availability) into another database, typically a local build into
production. It is three management commands in `apps/core/state_transfer.py`; there is no web
endpoint.

| Command | Where | Writes? |
|---|---|---|
| `export_state BUNDLE [--credentials FILE --existing-usernames a,b]` | the source | the bundle file (and the credentials file) only |
| `import_state BUNDLE [--dry-run] [--production-confirm]` | the target | the target database and media storage, in one transaction |
| `state_inventory [--resources CODES --days DATES --now ISO]` | either | nothing: counts and computed availability as JSON |

## What moves, and what never does

**Copied as is**, in dependency order: departments, blocks, resource types, features, resources
(with their `art` key), attributes, custodians, saved resources; booking policies, opening hours,
blackouts, quotas, the no-show ladder; terms, publications, timetable entries; maintenance windows
and breakdown reports; stock items, issuances and movements; booking series, bookings, booking
slots, booking attempts; workflows, steps, approvals; check-ins, no-shows, booking pauses;
utilisation snapshots; notifications. Uploaded files referenced by `Resource.image` and
`ResourceImage.image` travel inside the bundle and are written through Django's storage.

**Copied after sanitising:** people keep their name, username, email, VID, role, department and
profile fields, and every link to bookings, approvals and resources. They arrive without their
source password hash, MFA secret, last sign-in, lockout state, superuser or Django-staff flag, and
with a new calendar-feed token. Bookings arrive with new QR-pass tokens (a token opens the pass).

**Never copied:** sessions, the audit trail (the target keeps its own; the import adds one
`data.import_state` entry with counts), background-job runs, permissions and groups (each database
has its own; roles are re-applied), the secret key and every environment variable.

## Accounts and passwords

An account whose username already exists on the target is **never modified**: no new password, no
MFA change, no role change. The bundle's records are attached to it instead.

For the others, `export_state --credentials FILE --existing-usernames …` generates a fresh random
password per account (about 66 bits, typeable groups such as `Hk7m-Qp2r-Tz9w5`, checked against
`AUTH_PASSWORD_VALIDATORS`, all different). The plaintext goes **only** into `FILE`; the bundle
carries the Django hash. The command refuses a path inside the repository and never overwrites an
existing file, and prints no password. `.gitignore` and `.dockerignore` exclude
`*DEMO_CREDENTIALS*.md` and `*-state.json.gz` as a second guard. Without `--credentials`, new
accounts get an unusable password and an administrator sets one with `manage.py changepassword`.

Both commands print an `accounts_digest` of the usernames: the export for the accounts it issued
passwords to, the import for the accounts it created. Equal digests prove the credentials file lists
exactly the accounts that were created. Re-running the import never resets a password.

`--public-demo-vids V1,V2,V3 --public-demo-out FILE` marks a few accounts whose passwords will be
published (the README's demo accounts). Only new, active **Student** accounts qualify, so a
published credential can never be a privileged one; their passwords are generated like the rest,
and `FILE` holds just their VIDs and passwords (no names or emails). They sign in with the VID.

MFA follows the existing policy unchanged: administrators, facility managers and superusers enrol a
new authenticator at their first sign-in, protected by their new password; other roles do not.

## How rows are matched (idempotency)

A natural key where the schema has one (codes, references, one-row-per-booking links): the target
row is brought up to date. Otherwise the row's full contents after remapping, each target row
matched at most once, so identical source rows stay separate rows. New rows keep their source
primary key when the target has not used it. That keeps links that are not foreign keys
(`BookingSlot.source_type`/`source_id` pointing at timetable entries and maintenance windows) and
anything derived from an id (which curated photo `resource_photo` picks) the same; where a key is
taken, the database assigns one and every reference follows. Rows are written with bulk inserts and
queryset updates, so no signal, notification or email fires, and timestamps are kept. The search
index is rebuilt for the imported resources. A second run adds nothing.

The import refuses a bundle from a different set of migrations, stops on any reference the bundle
cannot satisfy, checks every deferred constraint before committing, and with DEBUG off writes only
with `--production-confirm`. `--dry-run` performs everything, then rolls back (and uploads no media).

## Running it against Railway

Production's database is private, so the import runs in the web container over `railway ssh`, and
the bundle travels on standard input:

```sh
# 1. Back up production first; restore it into a scratch PostgreSQL and compare counts before going on
railway ssh --service Django-EduRev-P20 -- sh -c \
  'python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission | gzip -9' \
  > prod-dumpdata-<UTC timestamp>.json.gz
# 2. Export locally, with the target's existing usernames
python manage.py export_state lpu-state.json.gz --existing-usernames swastik,Demo1 \
  --credentials "C:/Users/<you>/Desktop/LPU_RESERVE_DEMO_CREDENTIALS.md" \
  --public-demo-vids 12321411,12421707,12321744 --public-demo-out "C:/Users/<you>/Desktop/public-demo.md"
# 3. Rehearse, then import
railway ssh --service Django-EduRev-P20 -- sh -c 'cat > /tmp/s.gz && python manage.py import_state /tmp/s.gz --dry-run' < lpu-state.json.gz
railway ssh --service Django-EduRev-P20 -- sh -c 'cat > /tmp/s.gz && python manage.py import_state /tmp/s.gz --production-confirm; rm -f /tmp/s.gz' < lpu-state.json.gz
# 4. Compare: the same arguments on both sides must give the same digests
python manage.py state_inventory --resources 34-LAB-1,EQ-GPU-01 --days 2026-10-05 --now 2026-10-03T08:00:00+00:00
```

Bookings keep their absolute times, so "free at 10:00 on Monday" means the same on both sides; pass
the same `--now` to compare availability. Background sweeps on the target (no-show release,
reminders) act on the imported bookings from then on, as they would have on the source.
