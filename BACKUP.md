# VOC 백업과 복원

Linux VM의 rootful Podman과 시스템 systemd 기준이다. 백업은 Nginx와 웹 앱을 잠시 중지한 상태에서 PostgreSQL 덤프와 첨부 볼륨을 함께 복사한다. 이 시간에는 접속이 일시 중단된다. 별도 작업에서 DB나 첨부를 직접 수정한다면 같은 시간대의 실행을 피한다.

## 일일 백업 설정

1. VM **외부**의 백업 저장소를 VM 안에 마운트한다. 아래 예시의 `/mnt/voc-backup`을 실제 경로로 바꾼다. 외부 저장소는 운영 계정만 접근할 수 있게 설정한다. 목적지 하위 디렉터리는 백업 스크립트가 만든다. 스크립트는 외부 마운트가 빠졌을 때 빈 로컬 디렉터리에 기록하는 일을 막는다.
2. 프로젝트 루트에서 다음 명령을 실행한다. 실행 경로가 `/opt/voc`인 경우 첫 번째 파일 복사는 생략한다.

```bash
sudo install -d -m 0755 /opt/voc/deploy /etc/voc
sudo install -m 0755 deploy/backup.sh deploy/restore.sh /opt/voc/deploy/
sudo install -m 0644 deploy/voc-backup.service deploy/voc-backup.timer /etc/systemd/system/
sudo tee /etc/voc/backup.env >/dev/null <<'EOF'
BACKUP_MOUNT=/mnt/voc-backup
BACKUP_DIR=/mnt/voc-backup/snapshots
EOF
sudo systemctl daemon-reload
sudo systemctl start voc-backup.service
sudo journalctl -u voc-backup.service -n 20 --no-pager
sudo systemctl enable --now voc-backup.timer
systemctl list-timers voc-backup.timer
```

타이머는 VM 현지 시각 매일 03시에 실행된다. 완료된 디렉터리 이름은 UTC 시각이며 `db.dump`, `media.tar`, 사용한 이미지 이름과 ID, 체크섬을 담는다. 백업은 자동 삭제하지 않는다. 운영자는 저장 공간과 타이머 실패 여부를 확인한다. 웹 자격 증명 해시와 고객 첨부가 포함되므로 저장소의 접근 권한과 암호화를 운영 정책에 맞춰 설정한다.

## 독립 환경에서 복원 확인

현재 VM에서 운영 백업을 시험하려면 저장소의 `deploy/verify-restore.sh`와 `deploy/verify_restored_app.py`를 동일 디렉터리에 둔 상태에서 아래 명령을 실행한다. 검증 스크립트는 외부 포트가 없는 전용 네트워크와 별도 DB·첨부 볼륨을 만든다. 운영 백업을 복원해 마스터 로그인과 검증용 VOC·첨부 등록을 수행하고, 그 상태를 다시 백업해 두 번째 빈 DB·볼륨에 복원한 뒤 상세 조회와 첨부 바이트를 대조한다. 종료 시 임시 리소스를 정리한다. 백업 당시 이미지는 VM에 있어야 하며, 마스터 비밀번호를 변경했다면 백업 시점 비밀번호가 담긴 보호 파일 경로를 `VOC_MASTER_PASSWORD_FILE`에 지정한다.

```bash
sudo bash deploy/verify-restore.sh /mnt/voc-backup/snapshots/20261124T180000Z
```

전체 서비스와 HTTPS를 포함한 재해 복구 리허설은 별도 VM에서 다음 순서로 진행한다.

1. 운영 서비스가 실행 중인 VM과 분리된 **새 VM**에 동일한 배포 파일·이미지·Quadlet과 운영 설정을 준비한다. 백업의 `images.txt`에서 당시 버전을 확인한다. DB 계정 설정, TLS 인증서와 개인 키, Django 비밀 키, 컨테이너 이미지와 배포 파일은 별도 보안 저장소에서 확보한다. 인증서의 SAN과 복원 검증에 사용할 주소를 맞춘다.
2. 웹 앱이나 Nginx를 처음 기동하기 전에 유닛만 등록하고 `systemctl daemon-reload`를 실행한다. 설치 스크립트가 앱을 즉시 기동한다면 Quadlet 파일을 수동 배치한다. DB 및 첨부 대상은 비어 있어야 한다. 복원 명령이 DB를 먼저 시작하고 최종 단계에서 웹 앱과 Nginx를 시작한다.
3. 완성된 백업 디렉터리를 새 VM에서 읽을 수 있게 마운트한 후 아래 명령에 실제 경로를 넣는다.

```bash
sudo bash /opt/voc/deploy/restore.sh /mnt/voc-backup/snapshots/20261124T180000Z
sudo systemctl status voc-db voc-app voc-nginx --no-pager
```

4. 복원 직전에 기록한 테스트 VOC 번호와 첨부 원본의 SHA-256을 사용한다. HTTPS로 로그인한 뒤 해당 상세 페이지의 제기자·상태·처리 이력을 대조하고 첨부를 실제 다운로드한다. 다운로드 결과에 `sha256sum`을 실행해 원본과 비교한다. 재부팅 후 같은 조회와 다운로드를 반복한다.
5. 실패 시 터미널 오류와 `journalctl -u voc-db -u voc-app -u voc-nginx`를 확인한다. 복원이 중단되면 복원 VM에 부분 데이터가 남을 수 있으므로 원인을 수정한 뒤 새 빈 복원 환경에서 재시도한다. 기존 운영 볼륨을 삭제할 필요는 없다.
