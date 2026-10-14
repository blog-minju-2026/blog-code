# 한채 서버 배포

학원에서 받은 「서버 배포 설명서」(학원 공용 서버, 공개 저장소에는 올리지 않음)의 순서를 한채에 맞춘 안내다.
흐름: **main 에 올림 → GitHub Actions 가 Docker 이미지를 만듦 → 서버로 보냄 → SSH 로 `deploy.sh` 실행 → nginx 가 도메인을 내 포트로 연결.**

| 파일 | 하는 일 |
| --- | --- |
| `Dockerfile` · `.dockerignore` | Django + gunicorn 이미지. API 와 화면 파일(`*.html` · `css` · `js` · `assets`)을 함께 담는다. 컨테이너가 뜰 때 `migrate` 를 먼저 돌린다 |
| `.github/workflows/deploy.yml` | main 에 백엔드 · 화면 · 배포 파일이 바뀌면 자동 배포. Actions 탭에서 손으로도 돌릴 수 있다 |
| `deploy/deploy.sh` | 서버에서 실행: 이미지 불러오기 → 예전 컨테이너 내리기 → 새 컨테이너 띄우기 → 응답 확인 |
| `deploy/nginx/hanchae.conf.example` | nginx 설정 예시 |

## 1. GitHub Repository secrets 등록 (설명서 2단계)

저장소 → Settings → Secrets and variables → Actions → **Repository secrets** 에 아래 이름 그대로 넣는다.
값은 대화나 캡처로 남에게 보여 주지 않는다.

| 이름 | 넣을 값 | 어디서 |
| --- | --- | --- |
| `DB_ADDRESS` | DB 주소에서 뒤의 `:숫자` 를 뺀 부분 | Crowfoot → 데이터베이스 탭 → MySQL #1 (스키마 `cf_u37_d1`) |
| `DB_PORT` | 주소 뒤의 숫자 | 〃 |
| `DB_NAME` | 데이터베이스(스키마) 이름 | 〃 |
| `DB_USER` (또는 설명서의 `DB_USERNAME`) | 계정 | 〃 (설명서 표의 두 번째 `DB_NAME` 칸) |
| `DB_PASSWORD` | 비밀번호 | 〃 |
| `SSH_ADDRESS` | 서버 주소 (내부망 / 외부 핫스팟) | aip 프로젝트 공통 인프라 문서 |
| `SSH_ID` | 내 계정 | 〃 |
| `SSH_PASSWORD` | 공용 비밀번호 | 〃 |
| `SSH_PORT` | `8822` | 〃 |
| `APP_PORT` | **내 포트 번호** (설명서의 "자기 포트번호 맨 처음") | 공통 인프라 문서 |
| `HANCHAE_DOMAIN` | 받은 도메인 (예: `hanchae.java21.net`, `https://` 없이) | 〃 |
| `DJANGO_SECRET_KEY` | 긴 무작위 문자열. 아래 명령으로 만든다 | 직접 |
| `USE_HTTPS` | 도메인이 https 로 열리면 `1`, 아니면 비워 둔다 | 직접 |
| `EMAIL_HOST_USER` | 인증 메일을 보낼 한채 전용 Gmail 주소 (예: `hanchae.blog@gmail.com`) | 직접 |
| `EMAIL_HOST_PASSWORD` | 그 Gmail 의 **앱 비밀번호** 16자리 (계정 비밀번호가 아님). Google 계정 → 보안 → 2단계 인증을 켠 뒤 '앱 비밀번호'에서 만든다 | 직접 |

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # DJANGO_SECRET_KEY 값
```

## 2. 서버 준비 (설명서 3 · 5단계)

`SSH_ADDRESS` 는 접속하는 곳에 따라 다르다. 학교 와이파이(chosun_free 제외)에서는 내부망 주소, 핫스팟 · 집에서는 외부 주소 `s2.java21.net`. **GitHub Actions 는 학교 밖에서 접속하므로 Secret 에는 외부 주소를 넣는다.**

```bash
ssh -p 8822 <SSH_ID>@<SSH_ADDRESS>     # 처음 물으면 yes
docker --version                        # Docker 가 있는지 확인
mkdir -p ~/hanchae                      # 배포 파일이 놓일 곳
```

### nginx 설정 (설명서 5단계) — 서버의 공용 nginx 가 각자의 `~/nginx/*.conf` 를 읽어 도메인을 내 포트로 연결한다

```bash
mkdir -p ~/nginx
vi ~/nginx/hanchae.java21.net.conf      # 파일 이름 = 받은 도메인 + .conf
```

1. `i` 로 입력 모드에 들어가, **aip 프로젝트 문서에 있는 공용 설정의 `server { ... }` 를 그대로 붙여 넣는다.** (설정 원본은 그 문서에만 있다. 다른 사람 것을 따라 쓰지 않는다)
2. 두 군데를 바꾼다.
   - 3번째 줄 `server_name` → `hanchae.java21.net`
   - `proxy_pass` 의 `8300` → **GitHub Secrets 의 `APP_PORT` 와 같은 번호** (설명서: 자기 포트번호 맨 처음)
3. `server { ... }` 안에 **`client_max_body_size 12m;` 한 줄을 더한다.** 없으면 nginx 기본값(1MB) 때문에 사진 업로드가 막힌다.
4. `esc` → `:wq` 로 저장하고, `cat ~/nginx/hanchae.java21.net.conf` 로 바꾼 곳을 확인한다.

공용 nginx 가 모든 학생의 설정을 함께 읽으므로, 괄호 · 세미콜론이 빠진 설정은 다른 사람 사이트까지 멈추게 할 수 있다. 붙여 넣은 뒤 꼭 다시 확인한다. 참고 예시: `deploy/nginx/hanchae.conf.example`

컨테이너는 서버의 네트워크를 그대로 쓰는 방식(`--network host`)으로 떠서 `APP_PORT` 에서 바로 요청을 받는다. 학교 서버에서는 Docker 기본 네트워크에서 학교 내부망의 DB 로 가는 길이 막혀 있기 때문이다.

## 3. 첫 배포

1. 이 브랜치를 main 에 합치면 Actions 가 자동으로 돈다. (또는 Actions 탭 → deploy → Run workflow)
2. 실패하면 Actions 로그나 GitHub inbox 의 오류를 그대로 Claude 에게 보여 주고 고친다. 비밀 값은 지우고 보여 준다.
3. 성공하면 확인:
   - `http://<받은-도메인>/` → 마을 화면
   - `http://<받은-도메인>/api/topics` → 골목 10개
   - `http://<받은-도메인>/api/auth/me` → `{"user": null}`
4. 운영자 계정은 서버에서 한 번 만든다.

```bash
docker exec -it hanchae-backend python manage.py createsuperuser
```

## 알아 둘 것

- **업데이트**: 작업 브랜치 → PR → main 에 합치면 위 흐름이 다시 돈다. 백엔드(`backend/`)뿐 아니라 화면(`*.html` · `css/` · `js/` · `assets/`)만 바꿔도 배포된다.
- **노트북에서 이미지 확인**: 저장소 루트에서 `docker build -t hanchae-backend .` 후 `docker run --rm -p 8000:8000 --env-file backend/.env -e DB_HOST=host.docker.internal hanchae-backend`

- **테이블은 Django 가 만든다.** 컨테이너가 뜰 때마다 `migrate` 가 돈다. Crowfoot 화면의 "배포"로 테이블을 따로 만들지 않는다(두 곳에서 만들면 어긋난다).
- **올린 사진**은 서버의 `~/hanchae/media` 에 남는다. 컨테이너를 새로 띄워도 지워지지 않는다.
- **이미지 아키텍처**: Actions 는 `linux/amd64` 이미지를 만든다. 서버가 ARM 이면 `deploy.yml` 의 빌드에 `--platform` 을 맞춰야 한다.
- **한채 서브도메인**(`minju.<도메인>`)은 와일드카드 DNS 와 인증서가 있어야 한다. 안 되면 기능명세서 선택 7.3 을 경로 방식으로 바꾼다.
- **Crowfoot DB 정렬 규칙**: 발급된 스키마의 기본 정렬 규칙이 `utf8mb4_0900_as_ci` 가 아닐 수 있다. 첫 배포 뒤 확인하고, 다르면 태그 대소문자 처리(TAG-01)를 다시 확인한다.
