#!/usr/bin/env bash
#
# Encrypted PostgreSQL backup (P0.8).
#
# Produces a gzipped, AES-256 encrypted dump. The passphrase comes from the
# environment so it never lands in shell history or process args.
#
# Usage:
#   BACKUP_PASSPHRASE='...' ./scripts/backup.sh [output_dir]
#
# Output: <output_dir>/<db>_<UTC-timestamp>.sql.gz.enc   (default dir: ./backups)
#
# NOTE: the scheduled/automated run (cron) lives on the host once AWS hosting
# exists — this script is the unit it will call. Restore is restore.sh; test it
# monthly (a backup you've never restored is not a backup).
set -euo pipefail

DB_NAME="${DB_NAME:-crm_agents}"
DB_USER="${DB_USER:-richardfigueroa}"
OUT_DIR="${1:-./backups}"

: "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE to encrypt the backup}"

mkdir -p "$OUT_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUT_DIR/${DB_NAME}_${TS}.sql.gz.enc"

pg_dump -U "$DB_USER" "$DB_NAME" \
  | gzip \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE \
  > "$OUT"

echo "Backup written: $OUT ($(du -h "$OUT" | cut -f1))"
