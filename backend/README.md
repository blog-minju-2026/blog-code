# 한채 백엔드 (Django)

기능은 [기능명세서](https://github.com/blog-minju-2026/blog-docs/blob/main/docs/%EA%B8%B0%EB%8A%A5%EB%AA%85%EC%84%B8%EC%84%9C.md), API는 [API명세서](https://github.com/blog-minju-2026/blog-docs/blob/main/docs/API%EB%AA%85%EC%84%B8%EC%84%9C.md)(둘 다 blog-docs 저장소), DB는 Crowfoot ERD 「한채 블로그 플랫폼」을 따른다.

## 처음 한 번

```bash
# 1. Python 3.12, MySQL 8.4
brew install python@3.12 mysql@8.4
brew services start mysql@8.4

# 2. DB와 계정 (비밀번호는 직접 정한다)
mysql -u root -e "CREATE DATABASE hanchae CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci;
  CREATE USER 'hanchae'@'localhost' IDENTIFIED BY '<비밀번호>';
  GRANT ALL PRIVILEGES ON hanchae.* TO 'hanchae'@'localhost';
  GRANT ALL PRIVILEGES ON test_hanchae.* TO 'hanchae'@'localhost';"

# 3. 가상환경과 패키지 (mysqlclient 빌드에 MySQL 경로가 필요하다)
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
export MYSQLCLIENT_CFLAGS="-I/opt/homebrew/opt/mysql@8.4/include/mysql"
export MYSQLCLIENT_LDFLAGS="-L/opt/homebrew/opt/mysql@8.4/lib -lmysqlclient"
pip install -r requirements.txt
```

4. `backend/.env` 를 만든다 (git 에 올리지 않는다).

```
DJANGO_SECRET_KEY=<긴 무작위 문자열>
DJANGO_DEBUG=1
DB_NAME=hanchae
DB_USER=hanchae
DB_PASSWORD=<2에서 정한 비밀번호>
DB_HOST=127.0.0.1
DB_PORT=3306
# HANCHAE_DOMAIN=hanchae.kr   ← 서비스 도메인이 정해지면
# 인증 메일을 실제로 보내려면 (없으면 메일이 터미널에 찍힌다)
# EMAIL_HOST_USER=hanchae.blog@gmail.com
# EMAIL_HOST_PASSWORD=<Gmail 앱 비밀번호 16자리>
```

5. 테이블을 만든다: `python manage.py migrate` (골목 10개도 함께 들어간다)

## 자주 쓰는 명령

| 하는 일 | 명령 |
| --- | --- |
| 개발 서버 | `python manage.py runserver` → http://127.0.0.1:8000/django-admin/ |
| 운영자 계정 만들기 | `python manage.py createsuperuser` |
| 테스트 | `python manage.py test apps` |
| 모델을 바꾼 뒤 | `python manage.py makemigrations` → `python manage.py migrate` |

## 앱 구성

| 앱 | ERD 테이블 |
| --- | --- |
| `apps.accounts` | users (+ allauth 의 account_emailaddress, socialaccount_socialaccount) |
| `apps.blogs` | blogs |
| `apps.posts` | topics, categories, tags, posts, post_tags, images, post_images, post_views |
| `apps.community` | comments, guestbook_entries, post_likes, subscriptions |
| `apps.rankings` | ranking_snapshots, ranking_entries |
| `apps.moderation` | user_sanctions, admin_logs |

## ERD와 다른 점

- `created_at` · `updated_at` 은 DB 기본값(CURRENT_TIMESTAMP, ON UPDATE) 대신 Django 가 저장할 때 채운다.
- 외래 키의 ON DELETE(CASCADE, SET NULL, RESTRICT)는 DB 가 아니라 Django 가 처리한다.
- Django 권한 기능 때문에 ERD 에 없는 `users_groups`, `users_user_permissions` 테이블과 Django · allauth 의 기본 테이블이 함께 생긴다.
- 요청 횟수 · 로그인 실패 횟수를 세는 캐시 테이블 `cache_entries` 가 함께 생긴다 (`settings.CACHES`, migrate 가 만든다). 컨테이너 · gunicorn 작업자가 여럿이라 메모리 대신 DB 에 둔다.
