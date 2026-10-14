# 한채

한 사람이 한 채의 집을 짓고, 그 안에 기록을 쌓고, 이웃의 집을 찾아가는 블로그 서비스.

| 폴더 · 파일 | 내용 |
| --- | --- |
| `*.html` · `css/` · `js/` · `assets/` | 화면 (디자인 시스템 「한채」) |
| `backend/` | Django API ([backend/README.md](backend/README.md)) |
| `Dockerfile` · `docker-compose.yml` | 배포 이미지, 노트북에서 띄워 보기 |
| `deploy/` · `.github/workflows/deploy.yml` | 학교 서버 배포 ([deploy/README.md](deploy/README.md)) |

기능명세서 · API 명세서 같은 문서는 [blog-minju-2026/blog-docs](https://github.com/blog-minju-2026/blog-docs) 저장소에 있다.

## 노트북에서 Docker 로 띄워 보기

Docker Desktop 을 켠 뒤 저장소 루트에서:

```bash
docker compose up --build       # http://localhost:8000
```

- 학교 서버와 같은 배포 이미지 · 운영 설정(`DEBUG=0`) · MySQL 8.0.41 로 뜬다. DB 는 빈 상태에서 시작해 `migrate` 가 테이블을 만든다.
- 가입하면 인증 메일이 실제로 가지 않고 로그에 찍힌다. 링크 찾기: `docker compose logs app | grep verify-email`
- 끄기 `docker compose down` (DB · 사진은 남는다), 처음부터 다시 `docker compose down -v`

## 개발 서버로 띄우기

코드를 고치면서 바로 보려면 Docker 없이 Django 개발 서버를 쓴다. 준비는 [backend/README.md](backend/README.md).

```bash
cd backend && .venv/bin/python manage.py runserver   # http://127.0.0.1:8000
```

## 업데이트하고 릴리즈 노트 쓰기

1. 작업 브랜치에서 고친다 → PR → main 에 합치면 학교 서버로 자동 배포된다 ([deploy/README.md](deploy/README.md))
2. 사용자에게 알릴 변화가 있으면 같은 PR 에서 `assets/releases.json` 의 `releases` **맨 앞**에 새 항목을 더한다. 사이트의 '릴리즈' 버튼(`/releases`)에 보이고, 아직 안 본 사람에게는 버튼에 점이 뜬다.

```json
{
  "version": "1.2.0",
  "date": "2026-10-20",
  "title": "방명록이 생겼어요",
  "changes": [
    { "type": "new", "text": "한채마다 방명록을 남길 수 있어요." },
    { "type": "fixed", "text": "사진이 큰 기록이 늦게 뜨던 문제를 고쳤어요." }
  ]
}
```

- `type`: `new`(새 기능) · `improved`(좋아진 점) · `fixed`(고친 것) · `known`(알려진 문제)
- 버전은 새 기능이면 가운데 숫자(1.**2**.0), 고치기만 했으면 끝 숫자(1.1.**1**)를 올린다
- 사용자에게 보이는 글이라 해요체로, 화면에서 무엇이 달라졌는지를 쓴다
