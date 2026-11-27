#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

[[ $# == 1 ]] || { echo "Usage: restore.sh /path/to/backup" >&2; exit 2; }
source_dir=$(realpath -e -- "$1")
exec 9>/run/voc-maintenance.lock
flock -n 9 || { echo "Another maintenance operation is running." >&2; exit 1; }
(cd "$source_dir" && sha256sum --check --strict SHA256SUMS)
for unit in voc-app voc-nginx; do
    if systemctl is-active --quiet "$unit" || podman container exists "$unit"; then
        echo "Restore on an isolated VM with $unit stopped." >&2
        exit 1
    fi
done
systemctl start voc-db.service
for attempt in {1..60}; do
    if podman exec voc-db pg_isready --username=voc --dbname=voc >/dev/null; then break; fi
    sleep 1
done
tables=$(podman exec voc-db psql -XAt --username=voc --dbname=voc -c "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")
if [[ $tables != 0 ]]; then echo "Destination database contains tables." >&2; exit 1; fi
if ! podman volume exists voc-media; then podman volume create voc-media >/dev/null; fi
media_root=$(podman volume inspect --format '{{.Mountpoint}}' voc-media)
if [[ -n $(find "$media_root" -mindepth 1 -maxdepth 1 -print -quit) ]]; then
    echo "Destination media volume contains files." >&2
    exit 1
fi
podman volume import voc-media "$source_dir/media.tar"
podman exec -i voc-db pg_restore --username=voc --dbname=voc --no-owner --no-privileges --single-transaction < "$source_dir/db.dump"
systemctl start voc-app.service
systemctl start voc-nginx.service
echo "Restored database and media. Verify login, VOC details, and an attachment download."
