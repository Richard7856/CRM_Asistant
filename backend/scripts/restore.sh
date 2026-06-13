#!/usr/bin/env bash
#
# Restore an encrypted backup produced by backup.sh (P0.8).
#
# Usage:
#   BACKUP_PASSPHRASE='...' ./scripts/restore.sh <backup_file> <target_db>
#
# The target DB must already exist and should be EMPTY (createdb target_db first).
# Restoring into a fresh DB is also how you test that a backup is valid.
set -euo pipefail

BACKUP_FILE="${1:?Usage: restore.sh <backup_file> <target_db>}"
TARGET_DB="${2:?Usage: restore.sh <backup_file> <target_db>}"
DB_USER="${DB_USER:-richardfigueroa}"

: "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE to decrypt the backup}"

openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in "$BACKUP_FILE" \
  | gunzip \
  | psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$TARGET_DB"

echo "Restored $BACKUP_FILE into $TARGET_DB"
