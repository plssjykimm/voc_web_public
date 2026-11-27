#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${BACKUP_MOUNT:?Set BACKUP_MOUNT to the external backup mount point}"
: "${BACKUP_DIR:?Set BACKUP_DIR to a directory on that mount}"
mountpoint=$(realpath -e -- "$BACKUP_MOUNT")
destination=$(realpath -m -- "$BACKUP_DIR")
if [[ $mountpoint == / || $destination != "$mountpoint/"* ]] || ! mountpoint -q -- "$mountpoint"; then
    echo "External backup mount is missing or BACKUP_DIR is outside it." >&2
    exit 1
fi
install -d -m 0700 -- "$destination"
exec 9>/run/voc-maintenance.lock
flock -n 9 || { echo "Another maintenance operation is running." >&2; exit 1; }
for unit in voc-db voc-app voc-nginx; do systemctl is-active --quiet "$unit"; done
stamp=$(date -u +%Y%m%dT%H%M%SZ)
stage=$(mktemp -d -- "$destination/.partial-$stamp-XXXXXXXX")
resume=0
finish() {
    local result=$?
    trap - EXIT
    if (( resume )); then
        systemctl start voc-app.service && systemctl start voc-nginx.service || result=1
    fi
    if [[ -d $stage ]]; then rm -rf -- "$stage"; fi
    exit "$result"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM
podman inspect --format '{{.ImageName}} {{.Image}}' voc-app voc-db voc-nginx > "$stage/images.txt"
resume=1
systemctl stop voc-nginx.service
systemctl stop voc-app.service
podman exec voc-db pg_dump --username=voc --dbname=voc --format=custom > "$stage/db.dump"
podman volume export voc-media > "$stage/media.tar"
systemctl start voc-app.service
systemctl start voc-nginx.service
resume=0
(cd "$stage" && sha256sum db.dump media.tar images.txt > SHA256SUMS)
mv -T -- "$stage" "$destination/$stamp"
printf 'Backup complete: %s\n' "$destination/$stamp"
