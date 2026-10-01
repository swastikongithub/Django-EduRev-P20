#!/bin/sh
# Release step: runs once per deployment, in a one-off container built from the same image,
# before the new web release takes traffic (Railway "pre-deploy command"; scripts/ci/stack.sh
# runs the same steps in CI). Invoke through the entrypoint so it waits for PostgreSQL first:
#
#   sh /app/docker/entrypoint.sh sh /app/docker/predeploy.sh
#
# A non-zero exit stops the deployment and leaves the previous release serving.
set -eu

# 1. Refuse a configuration that would lose uploads or never send mail (apps/core/checks.py),
#    plus Django's own deployment errors. Warnings are printed but do not block.
python manage.py check --deploy --fail-level ERROR

# 2. Schema changes. Migrations are written to be backwards compatible with the release that is
#    still serving while this runs (docs/deployment-railway.md#migrations).
python manage.py migrate --noinput
