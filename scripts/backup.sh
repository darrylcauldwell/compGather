#!/usr/bin/env bash
# Database backup script for EquiCalendar
# Usage: ./scripts/backup.sh [backup_dir]
#
# Copies the SQLite database to a timestamped file and rotates old backups.
# Keeps the last 7 daily backups.
#
# Can be run from cron:
#   0 2 * * * /path/to/compGather/scripts/backup.sh
#
# Or via docker exec:
#   docker exec compgather /app/scripts/backup.sh /app/data/backups

set -euo pipefail

DB_PATH="${DB_PATH:-/app/data/compgather.db}"
BACKUP_DIR="${1:-/app/data/backups}"
KEEP_DAYS=7
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/compgather-${TIMESTAMP}.db"

# Create backup directory if needed
mkdir -p "${BACKUP_DIR}"

# Use SQLite's .backup command for a consistent copy (safe even while app is running)
if command -v sqlite3 &> /dev/null; then
    sqlite3 "${DB_PATH}" ".backup '${BACKUP_FILE}'"
else
    # Fallback: plain file copy (safe for SQLite in WAL mode if we copy both files)
    cp "${DB_PATH}" "${BACKUP_FILE}"
    [ -f "${DB_PATH}-wal" ] && cp "${DB_PATH}-wal" "${BACKUP_FILE}-wal"
    [ -f "${DB_PATH}-shm" ] && cp "${DB_PATH}-shm" "${BACKUP_FILE}-shm"
fi

# Rotate: delete backups older than KEEP_DAYS
find "${BACKUP_DIR}" -name "compgather-*.db" -mtime +${KEEP_DAYS} -delete 2>/dev/null || true
find "${BACKUP_DIR}" -name "compgather-*.db-wal" -mtime +${KEEP_DAYS} -delete 2>/dev/null || true
find "${BACKUP_DIR}" -name "compgather-*.db-shm" -mtime +${KEEP_DAYS} -delete 2>/dev/null || true

echo "Backup complete: ${BACKUP_FILE}"
ls -lh "${BACKUP_FILE}"
echo "Backups in ${BACKUP_DIR}:"
ls -1t "${BACKUP_DIR}"/compgather-*.db 2>/dev/null | head -10
