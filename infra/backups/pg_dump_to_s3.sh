#!/usr/bin/env sh
# Dump the live Postgres and push it to an S3-compatible bucket.
# Designed to run inside a tiny container or on the host crontab.
#
# Required env (read at execution time):
#   DATABASE_URL          full Postgres URL, including credentials
#   S3_ENDPOINT           e.g. https://<account>.r2.cloudflarestorage.com
#   S3_ACCESS_KEY / S3_SECRET_KEY / S3_BUCKET
#   BACKUP_PREFIX         optional, default "hiremesh"
#   RETENTION_DAYS        optional, default 30 (older objects pruned)
#
# Notes:
# - We use `pg_dump --format=custom`, gzipped, to keep restores easy.
# - Naming: <prefix>/<host>/<utc-date>/hiremesh-<utc-stamp>.dump.gz
# - The script exits non-zero on any failure so a wrapper (cron, systemd
#   timer, GitHub Actions, etc.) can alert on it.

set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${S3_ENDPOINT:?S3_ENDPOINT is required}"
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY is required}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY is required}"
: "${S3_BUCKET:?S3_BUCKET is required}"
PREFIX="${BACKUP_PREFIX:-hiremesh}"
RETENTION="${RETENTION_DAYS:-30}"

NOW_DATE=$(date -u +%Y-%m-%d)
NOW_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
HOST="${BACKUP_HOST_TAG:-default}"
KEY="${PREFIX}/${HOST}/${NOW_DATE}/hiremesh-${NOW_STAMP}.dump.gz"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "[backup] dumping database…"
pg_dump --format=custom --no-owner --no-privileges --dbname="$DATABASE_URL" \
  | gzip -c > "$TMP/dump.gz"

SIZE=$(wc -c < "$TMP/dump.gz")
echo "[backup] uploading $SIZE bytes to s3://${S3_BUCKET}/${KEY}"

mc alias set bk "$S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" >/dev/null
mc cp "$TMP/dump.gz" "bk/${S3_BUCKET}/${KEY}"

if [ "$RETENTION" -gt 0 ]; then
  echo "[backup] pruning objects older than ${RETENTION} days…"
  mc rm --recursive --force --older-than "${RETENTION}d" \
    "bk/${S3_BUCKET}/${PREFIX}/${HOST}/" || true
fi

echo "[backup] done."
