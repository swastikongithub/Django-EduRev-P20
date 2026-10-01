#!/usr/bin/env bash
# Backup -> restore drill against the running CI stack (scripts/ci/stack.sh up + seed):
# build the backup image for the stack's PostgreSQL major, take an encrypted backup into the S3
# emulator, fetch it, decrypt it with the private key, restore it into a fresh database and
# compare row counts with the live one. A backup that has never been restored is not a backup.
set -euo pipefail

NET="${NET:-lpr-ci}"
PG_MAJOR="${PG_MAJOR:-16}"
IMAGE="lpu-reserve-backup:ci"
DB_URL=postgres://edurev:edurev@db:5432
fail() { echo "BACKUP DRILL FAIL: $*" >&2; exit 1; }

docker build -q -f docker/backup/Dockerfile --build-arg PG_MAJOR="$PG_MAJOR" -t "$IMAGE" . >/dev/null
S3=(-e BACKUP_S3_BUCKET=lpr-backups -e BACKUP_S3_ENDPOINT_URL=http://s3:5000 -e BACKUP_S3_REGION=us-east-1
    -e BACKUP_S3_ACCESS_KEY_ID=ci-access-key -e BACKUP_S3_SECRET_ACCESS_KEY=ci-secret-key -e BACKUP_S3_ADDRESSING_STYLE=path)

# Everything after the backup runs in one throwaway container that holds the private key; the
# backup itself only ever sees the public recipient, as in production.
docker run --rm --network "$NET" "${S3[@]}" -e DB_URL="$DB_URL" -e PGPASSWORD=edurev \
    --user 0 --entrypoint sh "$IMAGE" -ec '
python3 -c "import boto3, os; boto3.client(\"s3\", endpoint_url=os.environ[\"BACKUP_S3_ENDPOINT_URL\"], region_name=\"us-east-1\", aws_access_key_id=\"x\", aws_secret_access_key=\"x\").create_bucket(Bucket=\"lpr-backups\")"
age-keygen -o /tmp/key.txt 2>/dev/null
RECIPIENT=$(age-keygen -y /tmp/key.txt)
DATABASE_URL=$DB_URL/edurev BACKUP_AGE_RECIPIENT=$RECIPIENT pgbackup.py backup
KEY=$(pgbackup.py list | awk "{print \$NF}" | head -1)
case "$KEY" in *.dump.age) ;; *) echo "backup was not encrypted: $KEY" >&2; exit 1;; esac
pgbackup.py fetch "$KEY" /tmp/b.age >/dev/null
age -d -i /tmp/key.txt /tmp/b.age > /tmp/b.dump
createdb -h db -U edurev restored
pg_restore --no-owner --exit-on-error --dbname="$DB_URL/restored" /tmp/b.dump
for t in bookings_booking bookings_bookingslot accounts_user catalogue_resource audit_auditlog django_migrations; do
    live=$(psql -XAtc "select count(*) from $t" "$DB_URL/edurev")
    restored=$(psql -XAtc "select count(*) from $t" "$DB_URL/restored")
    [ "$live" = "$restored" ] || { echo "$t: live $live, restored $restored" >&2; exit 1; }
    echo "ok   $t: $restored rows restored"
done
' || fail "see above"
echo "BACKUP DRILL PASS"
