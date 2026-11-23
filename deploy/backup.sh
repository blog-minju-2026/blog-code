#!/usr/bin/env bash
# 한채 백업. 서버에서 실행된다 (하루 한 번 .github/workflows/maintenance.yml 이 SSH 로 부른다. 손으로: bash ~/hanchae/backup.sh).
#
# - DB: 컨테이너 안의 mysqldump 로 통째로 떠서 ~/hanchae-backups/db-날짜.sql.gz 로 둔다. KEEP_DAYS(14일)보다 오래된 것은 지운다
# - 사진: ~/hanchae/media 를 ~/hanchae-backups/media 로 복사한다 (새 파일만). 서비스에서 지워진 사진은 바로 지우지 않고
#   ~/hanchae-backups/media-removed/날짜 로 옮겨 KEEP_DAYS 동안만 둔다 (실수로 지운 사진을 되찾을 수 있다)
# 지운 것(탈퇴한 회원의 정보 · 사진 등)도 KEEP_DAYS 가 지나면 백업에서 사라진다. 개인정보 처리방침 4장에 적은 기간과 같아야 한다.
#
# 출력은 공개 저장소의 Actions 로그에 남으므로 개수 · 크기만 쓴다 (주소 · 계정 같은 값은 쓰지 않는다).
# 백업은 같은 서버에 있다. 서버 디스크가 망가지면 함께 사라지므로, 가끔 노트북으로 내려받아 둔다 (deploy/README.md '백업').
set -euo pipefail

APP_DIR="$HOME/hanchae"
BACKUP_DIR="${BACKUP_DIR:-$HOME/hanchae-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"

# DB 의 이메일 · 비밀번호 해시가 들어 있다. 나만 읽게 한다
umask 077
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# 떠 있는 컨테이너 아무거나 (배포 중이면 하나는 내려가 있을 수 있다)
CONTAINER=""
for name in hanchae-backend-1 hanchae-backend-2; do
  if [ "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || true)" = "true" ]; then
    CONTAINER="$name"
    break
  fi
done
if [ -z "$CONTAINER" ]; then
  echo "떠 있는 한채 컨테이너가 없어 DB 를 백업하지 못했어요." >&2
  exit 1
fi

echo "[1/3] DB 백업"
DUMP="$BACKUP_DIR/db-$STAMP.sql.gz"
# 접속 값은 컨테이너가 이미 갖고 있는 환경 변수(hanchae.env)를 쓴다. 비밀번호는 명령 줄이 아니라 MYSQL_PWD 로 넘긴다.
# --single-transaction: 서비스를 멈추지 않고 한 시점의 모습으로 뜬다 (InnoDB)
# --skip-ssl-verify-server-cert: 이미지의 mysqldump 는 MariaDB 것이라 서버 인증서를 꼭 확인하려 든다.
#   학교 DB 의 인증서는 공인 인증서가 아니므로 끈다 (앱도 인증서를 확인하지 않고 붙는다)
# sed: MariaDB 의 mysqldump 가 첫 줄에 넣는 표시는 MySQL 로 되돌릴 때 오류가 나므로 뺀다
docker exec "$CONTAINER" sh -c '
  extra=""
  if mysqldump --version | grep -qi mariadb; then extra="--skip-ssl-verify-server-cert"; fi
  MYSQL_PWD="$DB_PASSWORD" mysqldump \
    --host="${DB_HOST:-$DB_ADDRESS}" --port="${DB_PORT:-3306}" --user="${DB_USER:-$DB_USERNAME}" \
    --single-transaction --quick --skip-lock-tables --no-tablespaces --default-character-set=utf8mb4 \
    $extra "$DB_NAME"
' | sed '1{/^\/\*M\{0,1\}!999999/d;}' | gzip > "$DUMP.part"

# 끝까지 떴는지 확인한다 (mysqldump 는 마지막 줄에 'Dump completed' 를 쓴다). 덜 뜬 파일은 남기지 않는다
if ! gunzip -c "$DUMP.part" | tail -n 1 | grep -q "Dump completed"; then
  rm -f "$DUMP.part"
  echo "DB 를 끝까지 뜨지 못했어요. 서버에서 bash ~/hanchae/backup.sh 로 오류를 확인하세요." >&2
  exit 1
fi
mv "$DUMP.part" "$DUMP"
echo "  DB 백업 $(du -h "$DUMP" | cut -f1)"

echo "[2/3] 사진 백업"
mkdir -p "$BACKUP_DIR/media"
if [ -d "$APP_DIR/media" ]; then
  # 새 파일 · 더 새로운 파일만 복사한다 (지우는 옵션은 주지 않는다). 사진 이름은 UUID 라 한 번 올린 파일은 바뀌지 않는다
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$APP_DIR/media/" "$BACKUP_DIR/media/"
  else
    cp -a -u "$APP_DIR/media/." "$BACKUP_DIR/media/"
  fi
fi
echo "  사진 백업 $(find "$BACKUP_DIR/media" -type f | wc -l | tr -d ' ')개 · $(du -sh "$BACKUP_DIR/media" | cut -f1)"

# 서비스에서 지워진 사진은 백업에서도 빼되, 바로 지우지 않고 날짜 폴더로 옮겨 둔다
REMOVED_DIR="$BACKUP_DIR/media-removed/$(date +%Y%m%d)"
moved=0
while IFS= read -r file; do
  if [ ! -e "$APP_DIR/media/$file" ]; then
    mkdir -p "$REMOVED_DIR/$(dirname "$file")"
    mv "$BACKUP_DIR/media/$file" "$REMOVED_DIR/$file"
    moved=$((moved + 1))
  fi
done < <(cd "$BACKUP_DIR/media" && find . -type f | sed 's|^\./||')
echo "  서비스에서 지워져 따로 옮긴 사진 ${moved}개"

echo "[3/3] 오래된 백업 정리 (${KEEP_DAYS}일보다 오래된 것)"
find "$BACKUP_DIR" -maxdepth 1 -name 'db-*.sql.gz.part' -mmin +60 -delete
find "$BACKUP_DIR" -maxdepth 1 -name 'db-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
if [ -d "$BACKUP_DIR/media-removed" ]; then
  # 폴더 이름이 옮긴 날짜다. 그날 뒤로는 건드리지 않으므로 수정 시각으로 오래된 것을 고른다
  find "$BACKUP_DIR/media-removed" -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP_DAYS" -exec rm -rf {} +
fi
find "$BACKUP_DIR/media" -mindepth 1 -type d -empty -delete
echo "  남은 DB 백업 $(find "$BACKUP_DIR" -maxdepth 1 -name 'db-*.sql.gz' | wc -l | tr -d ' ')개"
echo "백업 완료"
