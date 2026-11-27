#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mount=${1:?Usage: enable-backups.sh MOUNTPOINT BACKUP_DIRECTORY}
directory=${2:?Specify a directory on the external mount}
mountpoint -q -- "$mount"
case "$directory" in "$mount"/*) ;; *) echo 'Select a directory on the supplied mount.' >&2; exit 1;; esac
install -d -m 700 /etc/voc /opt/voc/deploy "$directory"
install -m 700 deploy/backup.sh deploy/restore.sh /opt/voc/deploy/
printf 'BACKUP_MOUNT="%s"\nBACKUP_DIR="%s"\n' "$mount" "$directory" > /etc/voc/backup.env
install -m 644 deploy/voc-backup.{service,timer} /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now voc-backup.timer
systemctl start voc-backup.service
