#!/usr/bin/env python3
"""
Logical PostgreSQL backups to a private S3-compatible bucket (Railway: a cron service).

    pgbackup.py backup           pg_dump -Fc | [age -r RECIPIENT] -> s3://BUCKET/PREFIX/<UTC stamp>.dump[.age]
                                 then delete backups older than BACKUP_RETENTION_DAYS
    pgbackup.py list             newest first
    pgbackup.py fetch KEY FILE   download one backup (decrypt it yourself with `age -d -i key.txt`)

Restoring is deliberately a manual, reviewed step: docs/backup-restore.md.

Environment
    DATABASE_URL                 the database to dump (Railway: ${{postgres.DATABASE_URL}})
    BACKUP_S3_BUCKET, BACKUP_S3_ENDPOINT_URL, BACKUP_S3_ACCESS_KEY_ID,
    BACKUP_S3_SECRET_ACCESS_KEY, BACKUP_S3_REGION
                                 the bucket (Railway: the bucket's BUCKET, ENDPOINT, ACCESS_KEY_ID,
                                 SECRET_ACCESS_KEY and REGION); a separate bucket from media is best
    BACKUP_S3_PREFIX             default "pg"
    BACKUP_RETENTION_DAYS        default 14; 0 keeps everything
    BACKUP_AGE_RECIPIENT         optional age public key (age1...). When set, dumps are encrypted
                                 before upload and only the holder of the private key can read
                                 them; the private key never goes near the platform.

The dump streams from pg_dump to the bucket without touching the container's disk.
"""

import datetime as dt
import os
import re
import subprocess
import sys

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config


def _env(name, default=None):
    value = os.environ.get(name, default)
    if value is None or value == "":
        sys.exit(f"pgbackup: {name} is not set")
    return value


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("BACKUP_S3_ENDPOINT_URL") or None,
        region_name=os.environ.get("BACKUP_S3_REGION") or None,
        aws_access_key_id=_env("BACKUP_S3_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("BACKUP_S3_SECRET_ACCESS_KEY"),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": os.environ.get("BACKUP_S3_ADDRESSING_STYLE", "virtual")},
            retries={"max_attempts": 5, "mode": "standard"},
        ),
    )


def _prefix():
    return os.environ.get("BACKUP_S3_PREFIX", "pg").strip("/")


def _major(version_text: str) -> int:
    return int(re.search(r"(\d+)", version_text).group(1))


def check_versions(url: str) -> None:
    """
    Client and server majors must match. pg_dump refuses a newer server, and a newer pg_dump writes
    settings an older server rejects on restore (e.g. 17's transaction_timeout on 16), which would
    only be discovered on the day the backup is needed.
    """
    client = _major(
        subprocess.run(["pg_dump", "--version"], capture_output=True, text=True, check=True).stdout.split()[-1]
    )
    server = subprocess.run(
        ["psql", url, "-XAtc", "SHOW server_version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if _major(server) != client:
        sys.exit(
            f"pgbackup: server is PostgreSQL {server} but pg_dump is {client}; rebuild with PG_MAJOR={_major(server)}"
        )


def backup() -> str:
    url = _env("DATABASE_URL")
    bucket = _env("BACKUP_S3_BUCKET")
    check_versions(url)
    recipient = os.environ.get("BACKUP_AGE_RECIPIENT", "").strip()
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    key = f"{_prefix()}/{stamp}.dump" + (".age" if recipient else "")

    dump = subprocess.Popen(
        ["pg_dump", "--format=custom", "--compress=6", "--no-owner", "--no-privileges", url], stdout=subprocess.PIPE
    )
    stream, enc = dump.stdout, None
    if recipient:
        enc = subprocess.Popen(
            ["age", "--encrypt", "--recipient", recipient], stdin=dump.stdout, stdout=subprocess.PIPE
        )
        dump.stdout.close()  # age owns the pipe now; pg_dump gets SIGPIPE if age dies
        stream = enc.stdout
    s3 = _s3()
    try:
        s3.upload_fileobj(stream, bucket, key, Config=TransferConfig(multipart_chunksize=16 * 1024 * 1024))
    finally:
        codes = [dump.wait()] + ([enc.wait()] if enc else [])
    if any(codes):
        s3.delete_object(Bucket=bucket, Key=key)  # never leave a truncated dump that looks valid
        sys.exit(f"pgbackup: dump failed (exit codes {codes}); partial upload removed")
    size = s3.head_object(Bucket=bucket, Key=key)["ContentLength"]
    print(f"pgbackup: wrote s3://{bucket}/{key} ({size} bytes{', encrypted' if recipient else ''})", flush=True)
    prune(s3, bucket)
    return key


def _objects(s3, bucket):
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=_prefix() + "/"):
        yield from page.get("Contents", [])


def prune(s3, bucket) -> None:
    days = int(os.environ.get("BACKUP_RETENTION_DAYS", "14"))
    if days <= 0:
        return
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    objects = sorted(_objects(s3, bucket), key=lambda o: o["LastModified"])
    # Always keep the newest backup, whatever its age.
    old = [o["Key"] for o in objects[:-1] if o["LastModified"] < cutoff]
    for key in old:
        s3.delete_object(Bucket=bucket, Key=key)
    if old:
        print(f"pgbackup: removed {len(old)} backup(s) older than {days} days", flush=True)


def main(argv):
    command = argv[1] if len(argv) > 1 else "backup"
    if command == "backup":
        backup()
    elif command == "list":
        s3 = _s3()
        for o in sorted(_objects(s3, _env("BACKUP_S3_BUCKET")), key=lambda o: o["LastModified"], reverse=True):
            print(f"{o['LastModified']:%Y-%m-%d %H:%M}Z  {o['Size']:>12}  {o['Key']}")
    elif command == "fetch" and len(argv) == 4:
        _s3().download_file(_env("BACKUP_S3_BUCKET"), argv[2], argv[3])
        print(f"pgbackup: saved {argv[2]} to {argv[3]}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
