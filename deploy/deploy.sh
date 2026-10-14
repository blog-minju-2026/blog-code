#!/usr/bin/env bash
# 서버에서 실행된다 (GitHub Actions 가 SSH 로 부른다).
# ~/hanchae 에 놓인 이미지 파일을 불러와, 같은 이미지로 컨테이너 두 개를 포트만 달리해 띄운다.
# nginx 가 두 포트를 upstream 으로 묶어 요청을 나눠 보낸다 (deploy/nginx/hanchae.conf.example).
# 하나씩 차례로 바꾸므로, 바꾸는 동안에도 다른 하나가 요청을 받는다.
set -euo pipefail

APP_DIR="$HOME/hanchae"
IMAGE="hanchae-backend:latest"
cd "$APP_DIR"
chmod 600 hanchae.env

APP_PORT="$(grep '^APP_PORT=' hanchae.env | cut -d= -f2-)"
APP_PORT_2="$(grep '^APP_PORT_2=' hanchae.env | cut -d= -f2-)"
if [ -z "$APP_PORT" ] || [ -z "$APP_PORT_2" ]; then
  echo "APP_PORT 또는 APP_PORT_2 가 비어 있어요. GitHub Secrets 를 확인하세요." >&2
  exit 1
fi
if [ "$APP_PORT" = "$APP_PORT_2" ]; then
  echo "APP_PORT 와 APP_PORT_2 가 같아요. 서로 다른 번호를 넣으세요." >&2
  exit 1
fi

# 컨테이너 하나를 새 이미지로 바꾸고, 응답할 때까지 기다린다
replace() {
  local name="$1" port="$2"

  docker rm -f "$name" >/dev/null 2>&1 || true
  # 호스트 네트워크로 띄운다. 학교 서버에서는 Docker 기본 네트워크(bridge)에서
  # 학교 내부망의 DB(10.116.x)로 가는 길이 막혀 있다 (No route to host). 서버 자신은 DB 에 닿는다.
  # 그래서 -p 대신 컨테이너가 서버의 포트에서 바로 받는다.
  # 사진 폴더는 두 컨테이너가 같은 곳을 쓴다.
  docker run -d \
    --name "$name" \
    --restart unless-stopped \
    --network host \
    --env-file "$APP_DIR/hanchae.env" \
    -e PORT="$port" \
    -v "$APP_DIR/media:/app/media" \
    "$IMAGE" >/dev/null

  # 첫 배포는 빈 DB 에 테이블을 만드느라(migrate) 오래 걸릴 수 있어 2분까지 기다린다
  for i in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:$port/api/topics" >/dev/null 2>&1 \
      && curl -fsS "http://127.0.0.1:$port/" >/dev/null 2>&1; then
      echo "  $name (포트 $port): /api/topics 와 / 응답 확인"
      return 0
    fi
    sleep 2
  done

  echo "$name 이 2분 안에 응답하지 않아요. 아래 로그를 확인하세요." >&2
  docker logs --tail 80 "$name" >&2
  return 1
}

echo "[1/4] 이미지 불러오기"
gunzip -c hanchae-backend.tar.gz | docker load
mkdir -p "$APP_DIR/media"

# 예전 이름(하나만 띄우던 때)의 컨테이너가 남아 있으면 내린다. 1번과 포트가 같다
docker rm -f hanchae-backend >/dev/null 2>&1 || true

# 1번이 먼저 뜨면서 migrate 를 끝내므로, 2번이 뜰 때는 할 일이 없다 (두 곳에서 동시에 migrate 하지 않는다)
echo "[2/4] 1번 컨테이너 바꾸기 (포트 $APP_PORT) — 그동안 2번이 요청을 받는다"
replace hanchae-backend-1 "$APP_PORT"

echo "[3/4] 2번 컨테이너 바꾸기 (포트 $APP_PORT_2) — 그동안 1번이 요청을 받는다"
replace hanchae-backend-2 "$APP_PORT_2"

echo "[4/4] 정리"
docker image prune -f >/dev/null 2>&1 || true
rm -f hanchae-backend.tar.gz
echo "배포 완료: 두 컨테이너 모두 응답 확인"
