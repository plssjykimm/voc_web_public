#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
[[ $# == 1 ]] || { echo "Usage: verify-restore.sh /path/to/completed/backup" >&2; exit 2; }
[[ $(id -u) == 0 ]] || { echo "Run inside the rootful Podman VM as root." >&2; exit 2; }
backup=$(realpath -e -- "$1")
helper=$(dirname "$(realpath -e -- "$0")")/verify_restored_app.py
master_file=${VOC_MASTER_PASSWORD_FILE:-/etc/g2r2-voc/master-initial-password}
: "${VOC_MASTER_USERNAME:?Set VOC_MASTER_USERNAME to the master account restored from backup}"
[[ -r $master_file && -r $helper ]]
(cd "$backup" && sha256sum --check --strict SHA256SUMS)
mapfile -t images < "$backup/images.txt"
app_image=${images[0]##* }
db_image=${images[1]##* }
for image in "$app_image" "$db_image"; do podman image exists "$image"; done
stage=$(mktemp -d /var/tmp/voc-verify-XXXXXXXXXX)
prefix=${stage##*/}
network=$prefix-net
containers=()
volumes=()
net_created=0
cleanup() {
    local result=$?
    trap - EXIT
    for c in "${containers[@]}"; do podman rm -f --ignore "$c" >/dev/null || result=1; done
    for v in "${volumes[@]}"; do podman volume rm "$v" >/dev/null || result=1; done
    if (( net_created )); then podman network rm "$network" >/dev/null || result=1; fi
    rm -rf -- "$stage"
    exit "$result"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
podman network create --internal "$network" >/dev/null
net_created=1
export POSTGRES_USER=voc POSTGRES_DB=voc
POSTGRES_PASSWORD=$(openssl rand -hex 32)
DJANGO_SECRET_KEY=$(openssl rand -hex 48)
export POSTGRES_PASSWORD DJANGO_SECRET_KEY
for phase in seed verify; do
    db=$prefix-$phase-db
    media=$prefix-$phase-media
    data=$prefix-$phase-data
    for volume in "$media" "$data"; do
        podman volume create "$volume" >/dev/null
        volumes+=("$volume")
    done
    podman run -d --pull=never --name "$db" --network "$network" \
        -e POSTGRES_USER -e POSTGRES_DB -e POSTGRES_PASSWORD \
        -v "$data:/var/lib/postgresql/data" "$db_image" >/dev/null
    containers+=("$db")
    for attempt in {1..90}; do
        if podman exec "$db" pg_isready -h 127.0.0.1 -U voc -d voc >/dev/null; then break; fi
        sleep 1
    done
    if [[ $phase == seed ]]; then source_dir=$backup; else source_dir=$stage; fi
    podman exec -i "$db" pg_restore -U voc -d voc --no-owner --no-privileges --single-transaction < "$source_dir/db.dump"
    podman volume import "$media" "$source_dir/media.tar"
    podman run --rm -i --pull=never --network "$network" -v "$media:/media/uploads:U" \
        -e POSTGRES_USER -e POSTGRES_DB -e POSTGRES_PASSWORD -e POSTGRES_HOST="$db" \
        -e DJANGO_SECRET_KEY -e DJANGO_SETTINGS_MODULE=config.settings -e DJANGO_ALLOWED_HOSTS=localhost \
        -e MEDIA_ROOT=/media/uploads -e VERIFY_ID="$prefix" -e VERIFY_PHASE="$phase" \
        -e VERIFY_MASTER="$VOC_MASTER_USERNAME" \
        "$app_image" python -c "$(cat "$helper")" < "$master_file"
    if [[ $phase == seed ]]; then
        podman exec "$db" pg_dump -U voc -d voc -Fc > "$stage/db.dump"
        podman volume export "$media" > "$stage/media.tar"
    fi
done
echo "Verified isolated restore, login, VOC detail, and byte-for-byte attachment recovery."
