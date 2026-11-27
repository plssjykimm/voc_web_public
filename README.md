# 사내 VOC 관리실 배포

회사 Linux VM의 `/src/voc_web`에 소스와 이미지를 보관합니다. Podman Compose가 PostgreSQL, Django/Gunicorn, Nginx를 하나의 프로젝트로 실행합니다. 예제는 rootful Podman 기준입니다.

Compose 실행기가 없는 서버에서는 [Podman 명령으로 직접 실행하는 절차](PODMAN-ONLY.md)를 사용합니다.

## 압축 파일 구성

`VOC-deploy-compose.tar.gz`의 최상위 디렉터리는 `voc_web/`입니다.

- `config/`, `voc/`, `templates/`, `static/`, `manage.py`는 앱 소스입니다. `requirements.txt`와 Containerfile은 이미지 재빌드에 사용합니다.
- `compose.yaml`, `deploy/compose-nginx.conf`는 실행 설정입니다.
- `images/voc-images.tar`에는 실행 이미지 3개와 재빌드용 Python·Nginx 베이스 이미지가 들어 있습니다.
- 회사 VM에서 새 DB와 첨부 볼륨을 생성합니다. 집에서 만든 테스트 데이터, 가상환경, 비밀번호, 인증서 개인 키는 압축 파일에 포함되지 않습니다.

## 최초 설치

Linux x86-64 VM에 Podman, Podman Compose, OpenSSL, curl, tar를 설치합니다. 검증에 사용한 버전은 Podman 6.1.4와 podman-compose 1.6.0입니다. Fedora에서는 `sudo dnf install podman podman-compose openssl curl tar`로 준비할 수 있습니다. 폐쇄망이라면 해당 VM의 OS 패키지를 미리 준비합니다.

아래 명령은 배포 파일을 현재 디렉터리에 복사해 두고 실행합니다. 처음 설치할 때만 압축을 풉니다.

```bash
sudo install -d /src
sudo tar -xzf VOC-deploy-compose.tar.gz -C /src
sudo chown -R "$(id -u):$(id -g)" /src/voc_web
cd /src/voc_web

sudo podman load -i images/voc-images.tar
```

다음 명령은 `.env`가 없을 때 설정을 생성합니다. 새 설치 후 같은 DB를 사용할 때는 `.env`에 저장된 DB 비밀번호를 유지합니다.

```bash
if [ ! -e .env ]; then
  read -r -p 'VOC 접속에 사용할 서버 IPv4 주소: ' VOC_SERVER_IP
  if [[ ! "$VOC_SERVER_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    echo '유효한 IPv4 주소를 입력해야 합니다.' >&2
    exit 1
  fi
  (
    umask 077
    printf 'VOC_SERVER_IP=%s\nPOSTGRES_PASSWORD=%s\nDJANGO_SECRET_KEY=%s\n' \
      "$VOC_SERVER_IP" "$(openssl rand -hex 32)" "$(openssl rand -hex 48)" > .env
  )
fi
if ! grep -q '^VOC_SERVER_IP=.' .env; then
  read -r -p 'VOC 접속에 사용할 서버 IPv4 주소: ' VOC_SERVER_IP
  if [[ ! "$VOC_SERVER_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    echo '유효한 IPv4 주소를 입력해야 합니다.' >&2
    exit 1
  fi
  printf '\nVOC_SERVER_IP=%s\n' "$VOC_SERVER_IP" >> .env
fi
set -a
. ./.env
set +a
```

회사 TLS 인증서와 키가 있으면 각각 `.runtime/tls/server.crt`와 `.runtime/tls/server.key`에 둡니다. 아직 인증서가 없다면 Bash에서 아래 명령으로 내부 CA와 IP 인증서를 생성합니다. 인증서를 갱신할 때는 발급 전에 기존 파일을 별도로 보관합니다.

```bash
(
  set -e
  umask 077
  mkdir -p .runtime/ca .runtime/tls
  openssl req -x509 -nodes -newkey rsa:3072 -sha256 -days 3650 \
    -subj '/CN=VOC Internal CA' \
    -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' \
    -addext 'keyUsage=critical,keyCertSign,cRLSign' \
    -keyout .runtime/ca/root.key -out .runtime/ca/root.crt
  openssl req -new -nodes -newkey rsa:2048 -subj "/CN=$VOC_SERVER_IP" \
    -keyout .runtime/tls/server.key -out .runtime/tls/server.csr
  openssl x509 -req -in .runtime/tls/server.csr \
    -CA .runtime/ca/root.crt -CAkey .runtime/ca/root.key -CAcreateserial \
    -days 365 -sha256 -out .runtime/tls/server.crt \
    -extfile <(printf '%s\n' 'basicConstraints=critical,CA:FALSE' \
      'extendedKeyUsage=serverAuth' 'keyUsage=critical,digitalSignature,keyEncipherment' \
      "subjectAltName=IP:$VOC_SERVER_IP,IP:127.0.0.1,DNS:localhost")
)
```

## 실행과 재시작

모든 Compose 명령은 `/src/voc_web`에서 실행합니다. `up -d`가 DB 준비 확인, 스키마 적용, 앱 실행, Nginx 실행 순으로 전체 서비스를 시작합니다. `migrate`는 적용을 끝내면 종료되는 작업입니다.

```bash
sudo podman-compose up -d
read -r -p '최초 마스터 계정명: ' MASTER_USERNAME
sudo podman-compose exec app python manage.py bootstrap --master "$MASTER_USERNAME"
sudo podman-compose ps
curl --cacert .runtime/ca/root.crt -fsS -o /dev/null -w '%{http_code}\n' https://localhost:8989/login
```

`bootstrap`은 최초 설치 때 실행하고 프롬프트에서 마스터 비밀번호를 정합니다. 마스터 비밀번호를 바꿀 때 같은 명령을 사용할 수 있습니다. 회사에서 발급한 인증서를 쓰면 위 curl 명령에 회사 CA 파일을 지정합니다.

- 전체 중지와 재기동은 각각 `sudo podman-compose stop`, `sudo podman-compose up -d`입니다. 개별 컨테이너에 대한 `podman start`는 나머지 서비스를 시작하지 않습니다.
- DB, Django, Nginx는 비정상 종료 시 재시작합니다. VM 부팅 때도 자동 재시작하려면 운영 Linux VM에서 `sudo systemctl enable podman-restart.service`를 설정합니다. 사용자가 직접 중지한 서비스는 `up -d`로 다시 올립니다.
- PostgreSQL과 첨부는 Podman 영구 볼륨에 저장합니다. `down -v`는 운영 볼륨까지 삭제합니다.

운영 서버의 TCP 8989를 VM의 TCP 8989로 전달합니다. Windows Podman VM을 쓰면 관리자 PowerShell에서 다음과 같이 서버 IPv4 주소와 VM 이름을 입력해 포트 전달을 설정합니다.

```powershell
$serverIp = Read-Host "사내망 접속에 사용할 서버 IPv4 주소"
$machineName = Read-Host "Podman VM 이름"
.\deploy\windows\Connect-OperatingNetwork.ps1 -ServerAddress $serverIp -MachineName $machineName
```

위에서 생성한 공개 CA 인증서 `.runtime/ca/root.crt`를 접속 PC가 신뢰하도록 등록한 뒤 `https://<서버 IPv4 주소>:8989/login`으로 접속해 운영 설비를 등록합니다.

## 회사에서 수정하고 반영하기

`/src/voc_web`의 소스와 정적 파일은 컨테이너에 읽기 전용으로 마운트됩니다. 회사 서버에서 이 디렉터리의 파일을 편집합니다.

- Python 및 템플릿을 수정한 뒤 `sudo podman-compose restart app`을 실행합니다. CSS와 JavaScript는 Nginx가 마운트에서 읽으며 브라우저에서 강력 새로고침해 확인합니다.
- 모델 마이그레이션 파일을 추가했으면 `sudo podman-compose run --rm migrate`로 적용한 후 앱을 재시작합니다.
- Python 패키지가 바뀌면 같은 디렉터리에서 `sudo podman build -t localhost/g2r2-voc:1 -f Containerfile .`로 앱 이미지를 다시 빌드하고 `sudo podman-compose up -d --force-recreate`를 실행합니다. 새 패키지를 내려받을 수 있는 네트워크나 사내 패키지 저장소가 필요합니다.
