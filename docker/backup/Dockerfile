# Nightly logical backup of the LPU Reserve database (docs/backup-restore.md).
# Railway: a cron service built from this file (.railway/railway.ts, service "backup").
# Build context is the repository root: docker build -f docker/backup/Dockerfile .
#
# PG_MAJOR must equal the server's major version (`SHOW server_version`); the script refuses to
# run otherwise, so a dump is always restorable into the server it came from. On Railway a
# service variable named PG_MAJOR is passed to the build as this argument.
ARG PG_MAJOR=17
FROM postgres:${PG_MAJOR}-alpine

RUN apk add --no-cache python3 py3-boto3 age \
    && adduser -D -H -u 10002 backup

COPY --chmod=0555 docker/backup/pgbackup.py /usr/local/bin/pgbackup.py

USER backup
ENTRYPOINT ["python3", "/usr/local/bin/pgbackup.py"]
CMD ["backup"]
