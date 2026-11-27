# Compose 없이 VOC 실행

회사 Linux VM에 Podman만 있는 경우의 절차입니다. 기존 배포 압축 파일의 이미지와 소스를 사용합니다. 아래 명령은 Bash에서 실행합니다.

## 처음 한 번

배포 파일을 이미 풀었다면 `cd /src/voc_web`부터 실행합니다.

```bash
sudo install -d /src
sudo tar -xzf VOC-deploy-compose.tar.gz -C /src
sudo chown -R "$(id -u):$(id -g)" /src/voc_web
cd /src/voc_web
sudo podman load -i images/voc-images.tar
```

압축 안의 README에 따라 `.env`와 `.runtime/tls/server.crt`, `.runtime/tls/server.key`를 준비합니다. `.env`에는 서버 IPv4 주소, 새 DB 비밀번호, Django 비밀 키가 들어갑니다. 다음 명령으로 설정을 읽습니다.

```bash
set -a
. ./.env
set +a
: "${VOC_SERVER_IP:?Set VOC_SERVER_IP in .env}"
```

기존 VOC가 8989 포트를 사용 중이면 먼저 그 배포를 중지합니다.

다음 명령은 같은 Pod에서 앱과 Nginx가 루프백 주소로 통신하도록 프록시 설정을 만듭니다.

```bash
sed -e '/^[[:space:]]*resolver /d' \
    -e '/^[[:space:]]*set \$app /d' \
    -e 's|proxy_pass http://\$app:8000;|proxy_pass http://127.0.0.1:8000;|' \
    deploy/compose-nginx.conf > .runtime/pod-nginx.conf

sudo podman pod create --name voc-web --publish 8989:443
sudo podman volume create voc-web-db
sudo podman volume create voc-web-media
```

DB와 앱을 차례로 등록합니다. 포함된 앱 이미지가 PostgreSQL 접속을 기다린 뒤 스키마를 적용하고 Gunicorn을 실행합니다.

```bash
sudo podman run -d --name voc-web-db --pod voc-web --pull=never \
  --restart=unless-stopped \
  --env-file .env -e POSTGRES_DB=voc -e POSTGRES_USER=voc \
  -v voc-web-db:/var/lib/postgresql/data \
  docker.io/library/postgres:16-alpine

sudo podman run -d --name voc-web-app --pod voc-web --pull=never \
  --restart=unless-stopped --requires voc-web-db \
  --env-file .env -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=voc -e POSTGRES_USER=voc \
  -e "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,${VOC_SERVER_IP}" -e MEDIA_ROOT=/media/uploads \
  -v /src/voc_web/manage.py:/app/manage.py:ro,z \
  -v /src/voc_web/config:/app/config:ro,z \
  -v /src/voc_web/voc:/app/voc:ro,z \
  -v /src/voc_web/templates:/app/templates:ro,z \
  -v /src/voc_web/static:/app/static:ro,z \
  -v voc-web-media:/media/uploads:U \
  localhost/g2r2-voc:1

sudo podman run -d --name voc-web-nginx --pod voc-web --pull=never \
  --restart=unless-stopped --requires voc-web-app \
  -v /src/voc_web/static:/usr/share/nginx/html/static:ro,z \
  -v /src/voc_web/.runtime/pod-nginx.conf:/etc/nginx/conf.d/default.conf:ro,z \
  -v /src/voc_web/.runtime/tls:/etc/voc-tls:ro,z \
  localhost/g2r2-voc-nginx:1

sudo podman logs --tail 25 voc-web-app
```

앱 로그에서 Gunicorn 기동을 확인한 뒤 마스터 비밀번호를 정합니다. 내부 CA를 발급했다면 아래 curl 명령으로 HTTPS를 확인합니다.

```bash
read -r -p '최초 마스터 계정명: ' MASTER_USERNAME
sudo podman exec -it voc-web-app python manage.py bootstrap --master "$MASTER_USERNAME"
curl --cacert .runtime/ca/root.crt -fsS -o /dev/null -w '%{http_code}\n' https://localhost:8989/login
```

## 이후 시작과 중지

```bash
sudo podman pod stop voc-web
sudo podman pod start voc-web
sudo podman ps --pod
```

`pod start` 한 번으로 DB, Django, Nginx를 함께 시작합니다. Python이나 템플릿을 수정한 뒤에는 `sudo podman restart voc-web-app`을 실행합니다. 사용자 PC에서는 `https://<서버 IPv4 주소>:8989/login`으로 접속합니다.
