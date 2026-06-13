# Ops scripts (P0.8)

## Backups — `backup.sh` / `restore.sh`

Encrypted PostgreSQL dumps: `pg_dump | gzip | openssl aes-256`. The passphrase
comes from `BACKUP_PASSPHRASE` (env) so it never hits shell history.

```bash
# Create a backup of the dev DB
BACKUP_PASSPHRASE='your-strong-passphrase' ./scripts/backup.sh ./backups

# Restore into a fresh DB (this is also how you VERIFY a backup)
createdb crm_agents_restore_test
BACKUP_PASSPHRASE='your-strong-passphrase' \
  ./scripts/restore.sh ./backups/crm_agents_<ts>.sql.gz.enc crm_agents_restore_test
```

**Pending (needs hosting):** the *scheduled* nightly run (cron) and offsite
storage live on the host once AWS is set up. These scripts are the unit that cron
will call. **A backup you've never restored is not a backup — test restore monthly.**

The encryption passphrase must be stored separately from the backups (e.g. a
secrets manager). Losing it makes every backup unreadable.

## `sync_dev_enum_labels.py`

One-shot dev fix for the enum NAMES-vs-VALUES inconsistency in old migrations.
Adds any missing member-name labels to existing Postgres enum types so the dev DB
accepts what the ORM binds. Idempotent, non-destructive.

```bash
python -m scripts.sync_dev_enum_labels   # from backend/, venv active
```
