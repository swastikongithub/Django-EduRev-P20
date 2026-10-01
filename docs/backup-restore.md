# Backup and restore on Railway

How the production database is backed up on Railway and how to restore it. For docker compose
and general procedures, see the [runbook](runbook.md#backup). CES §1.3 asks for a documented,
tested restore; CI performs the drill below on every push.

## What is backed up

| Data | Mechanism | Retention | Restores to |
|---|---|---|---|
| PostgreSQL (all application data, including the audit log) | Railway **volume backups** of the `postgres` service (enable in the dashboard → postgres → Backups) | daily 6 days, weekly 27 days, monthly 89 days | a new volume mounted in place of the old one; the old volume is kept, unmounted |
| PostgreSQL, logically | the **`backup` cron service** (`docker/backup/`): nightly at 02:00 IST, `pg_dump --format=custom`, optionally age-encrypted, streamed into the private `backups` bucket | 14 days (`BACKUP_RETENTION_DAYS`); the newest dump is never pruned | any PostgreSQL of the same major version, anywhere |
| Uploaded resource photos | stored in the private `media` bucket, outside every container | the bucket (Railway buckets have no versioning) | n/a |
| Redis | not backed up: cache entries and queued tasks only | | |

The two database layers fail differently. Volume backups are fast to restore but live in the
same project as the database. Logical dumps are portable and can be decrypted only by whoever
holds the private age key. Volume backups need nothing beyond the dashboard toggle. The cron
dumps need the steps below.

## Setting up the logical backups

1. **Generate an age key pair** on a trusted machine (`age-keygen -o lpu-reserve-backup.key`). It
   prints the public key (`age1…`).
2. Store the **private key** file offline with two custodians, for example the university's
   password manager or vault. It is never put on Railway: losing it makes every encrypted dump
   unreadable, and leaking it exposes them.
3. Set the shared variable `BACKUP_AGE_RECIPIENT` to the **public** key.
4. Set `PG_MAJOR` on the `backup` service to the PostgreSQL major version
   (`railway connect postgres`, then `SHOW server_version;`). The script refuses to run with a
   mismatched `pg_dump`. A newer `pg_dump` writes settings that an older server rejects on
   restore, which would only be found on the day the backup is needed.
5. Trigger the `backup` service once from the dashboard and check its log:
   `pgbackup: wrote s3://…/pg/<UTC stamp>.dump.age (… bytes, encrypted)`.

Without `BACKUP_AGE_RECIPIENT` the dumps are stored unencrypted, in a private bucket that only
the project's credentials can read. Encrypting them is strongly recommended: the database holds
personal data (names, university IDs, email addresses; see [security-review.md](security-review.md)).

## Restoring

Always restore into a **new, empty** database, verify it, then switch the application over.
Never restore over the live database.

### From a Railway volume backup

Dashboard → `postgres` → Backups → choose the backup → Restore, then review the staged change
and click **Deploy**. Railway mounts the snapshot as a new volume and keeps the current one
unmounted, so this step is reversible until the old volume is deleted. Stop `worker` and `beat`
first, so sweeps do not act on a database that is rolling back. Then check `/ready/` and the
[verification queries](runbook.md#tested-restore-procedure).

### From a logical dump

On a trusted machine with Docker, the private key and the `backups` bucket's credentials
(dashboard → backups → Credentials):

```bash
docker build -f docker/backup/Dockerfile --build-arg PG_MAJOR=<major> -t lpr-backup .
export BACKUP_S3_BUCKET=… BACKUP_S3_ENDPOINT_URL=… BACKUP_S3_ACCESS_KEY_ID=… BACKUP_S3_SECRET_ACCESS_KEY=… BACKUP_S3_REGION=auto
B="-e BACKUP_S3_BUCKET -e BACKUP_S3_ENDPOINT_URL -e BACKUP_S3_ACCESS_KEY_ID -e BACKUP_S3_SECRET_ACCESS_KEY -e BACKUP_S3_REGION"

docker run --rm $B lpr-backup list                                  # newest first
docker run --rm $B -v "$PWD:/work" --user 0 lpr-backup fetch pg/<stamp>.dump.age /work/restore.dump.age
age -d -i lpu-reserve-backup.key restore.dump.age > restore.dump   # skip for unencrypted dumps
pg_restore -l restore.dump | head                                   # the archive lists its contents
```

Then create an empty database (a new Railway PostgreSQL service, or `CREATE DATABASE` on the
existing one) and restore into it over its **public** URL:

```bash
pg_restore --no-owner --exit-on-error --dbname "<DATABASE_PUBLIC_URL of the new database>" restore.dump
```

Verify the restore with the [runbook's checks](runbook.md#tested-restore-procedure): row counts,
`SELECT count(*) FROM django_migrations`, and a booking overlap check that must return 0. Then
stop `worker` and `beat`, point the `DATABASE_URL` reference of `web`, `worker`, `beat` and
`backup` at the new database, and redeploy. Delete `restore.dump` and `restore.dump.age` afterwards.

## The drill in CI

`scripts/ci/backup_roundtrip.sh` runs in the `docker` job after the smoke test:

1. Seed the demo campus into the production-like stack.
2. Generate a throwaway age key.
3. Run the real backup image, which encrypts the dump with the public key and uploads it to an
   S3 emulator.
4. Fetch the dump and decrypt it with the private key.
5. `pg_restore --exit-on-error` into a fresh database.
6. Compare row counts for bookings, slots, users, resources, the audit log and migrations.

A failure fails the build. Run it by hand against a local stack with
`scripts/ci/stack.sh up && scripts/ci/stack.sh seed && scripts/ci/backup_roundtrip.sh`.
