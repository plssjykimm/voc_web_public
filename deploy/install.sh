#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
config=/etc/g2r2-voc
if [[ $(id -u) != 0 ]]; then echo 'Run as root inside the dedicated VM.' >&2; exit 1; fi
public_ip=${VOC_SERVER_IP:-}
if [[ -z "$public_ip" ]]; then
    read -r -p 'VOC 접속에 사용할 서버 IPv4 주소: ' public_ip
fi
if [[ ! "$public_ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then echo 'Enter a valid IPv4 address.' >&2; exit 1; fi
master=${VOC_MASTER_USERNAME:-}
if [[ -z "$master" ]]; then
    read -r -p '최초 마스터 계정명: ' master
fi
if [[ -z "$master" ]]; then echo 'A master username is required.' >&2; exit 1; fi
command -v openssl >/dev/null || { echo 'Install openssl in the VM before setup.' >&2; exit 1; }
for image in docker.io/library/postgres:16-alpine localhost/g2r2-voc:1 localhost/g2r2-voc-nginx:1; do
    podman image exists "$image" || { echo "Missing image $image" >&2; exit 1; }
done
install -d -m 700 "$config" "$config/tls" "$config/ca"
if ! grep -q '^POSTGRES_PASSWORD=.' "$config/db.env" 2>/dev/null; then
    password=$(openssl rand -hex 32)
    {
        echo POSTGRES_HOST=voc-db
        echo POSTGRES_DB=voc
        echo POSTGRES_USER=voc
        echo "POSTGRES_PASSWORD=$password"
    } > "$config/db.env"
fi
if ! grep -q '^DJANGO_SECRET_KEY=.' "$config/app.env" 2>/dev/null; then
    secret=$(openssl rand -hex 48)
    {
        echo "DJANGO_SECRET_KEY=$secret"
        echo "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,$public_ip"
        echo MEDIA_ROOT=/media/uploads
        echo "VOC_EQUIPMENT=${VOC_EQUIPMENT:-}"
    } > "$config/app.env"
fi
if [[ ! -s "$config/ca/root.crt" ]]; then
    openssl req -x509 -nodes -newkey rsa:3072 -sha256 -days 3650 -subj '/CN=G2R2 VOC Internal CA' \
      -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' -addext 'keyUsage=critical,keyCertSign,cRLSign' \
      -keyout "$config/ca/root.key" -out "$config/ca/root.crt"
fi
if [[ ! -s "$config/tls/server.crt" ]]; then
    openssl req -new -nodes -newkey rsa:2048 -subj "/CN=$public_ip" \
      -keyout "$config/tls/server.key" -out "$config/tls/server.csr"
    openssl x509 -req -in "$config/tls/server.csr" -CA "$config/ca/root.crt" -CAkey "$config/ca/root.key" \
      -CAcreateserial -days 365 -sha256 -out "$config/tls/server.crt" \
      -extfile <(printf '%s\n' 'basicConstraints=critical,CA:FALSE' 'extendedKeyUsage=serverAuth' \
      'keyUsage=critical,digitalSignature,keyEncipherment' "subjectAltName=IP:$public_ip,IP:127.0.0.1,DNS:localhost")
fi
install -d /etc/containers/systemd
install -m 644 deploy/quadlet/* /etc/containers/systemd/
install -m 644 deploy/voc-startup.{service,timer} /etc/systemd/system/
systemctl daemon-reload
systemctl start voc-app.service
for attempt in {1..90}; do
    if podman exec voc-app python -c "import socket; socket.create_connection(('localhost',8000),1).close()" 2>/dev/null; then break; fi
    if [[ $attempt == 90 ]]; then echo 'Application startup timed out.' >&2; exit 1; fi
    sleep 1
done
if [[ ! -f "$config/master-initial-password" ]]; then openssl rand -hex 20 > "$config/master-initial-password"; fi
podman exec -i --env "MASTER_USERNAME=$master" voc-app python -c \
  'import os, sys; os.environ["MASTER_PASSWORD"]=sys.stdin.readline().strip(); os.environ["DJANGO_SETTINGS_MODULE"]="config.settings"; import django; django.setup(); from django.core.management import call_command; call_command("bootstrap")' < "$config/master-initial-password"
systemctl restart voc-nginx.service
systemctl enable --now voc-startup.timer
curl --retry 15 --retry-connrefused --retry-delay 1 --cacert "$config/ca/root.crt" -fsS -o /dev/null https://localhost:8989/login
echo "Ready: https://localhost:8989/login"
