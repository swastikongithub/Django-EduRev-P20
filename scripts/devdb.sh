#!/usr/bin/env bash
# Local development PostgreSQL without Docker: a throwaway cluster in .devdb/ on port 5433.
# Usage: scripts/devdb.sh init|start|stop|psql
# PG_BIN defaults to the Windows installer path; override for macOS/Linux (e.g. PG_BIN=/usr/lib/postgresql/16/bin).
set -euo pipefail
PG_BIN="${PG_BIN:-/c/Program Files/PostgreSQL/18/bin}"
DATA=".devdb/data"
PORT="${PGPORT:-5433}"

case "${1:-start}" in
  init)
    "$PG_BIN/initdb" -D "$DATA" -U edurev --auth=trust -E UTF8 --locale=C
    # 500-way concurrency test needs headroom above the default 100 connections.
    sed -i 's/^#\?max_connections = .*/max_connections = 700/' "$DATA/postgresql.conf"
    "$0" start
    sleep 3
    "$PG_BIN/createdb" -h localhost -p "$PORT" -U edurev edurev
    ;;
  start) "$PG_BIN/pg_ctl" -D "$DATA" -o "-p $PORT" -l .devdb/pg.log start ;;
  stop) "$PG_BIN/pg_ctl" -D "$DATA" stop ;;
  psql) "$PG_BIN/psql" -h localhost -p "$PORT" -U edurev edurev ;;
  *) echo "usage: $0 init|start|stop|psql" >&2; exit 2 ;;
esac
