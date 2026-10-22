"""
한채 Django 설정.

비밀 값과 환경마다 다른 값은 backend/.env 에서 읽는다(.env 는 git 에 올리지 않는다).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    return os.environ.get(name, default)


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG", "0") == "1"

# 서비스 도메인. 배포할 때 받은 도메인을 HANCHAE_DOMAIN 에 넣는다(예: hanchae.java21.net).
HANCHAE_DOMAIN = env("HANCHAE_DOMAIN", "")
# 사이트가 https 로 열리면 1. 로그인 · CSRF 쿠키를 https 에서만 보낸다.
# http 로만 열리는 사이트에 1 을 넣으면 쿠키가 저장되지 않아 로그인이 안 된다.
USE_HTTPS = env("USE_HTTPS", "0") == "1"
SCHEME = "https" if USE_HTTPS else "http"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".localhost"]
if HANCHAE_DOMAIN:
    ALLOWED_HOSTS += [HANCHAE_DOMAIN, f".{HANCHAE_DOMAIN}"]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 외부 패키지
    "rest_framework",
    "corsheaders",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.kakao",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.naver",
    # 한채
    "apps.accounts",
    "apps.blogs",
    "apps.posts",
    "apps.community",
    "apps.rankings",
    "apps.moderation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.common.middleware.SuspendedUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # backend/templates 의 파일이 패키지(allauth 등)의 같은 이름 템플릿보다 먼저 쓰인다
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# 데이터베이스: MySQL 8.4, utf8mb4 / utf8mb4_0900_as_ci (ERD REQ-001)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME", "hanchae"),
        "USER": env("DB_USER") or env("DB_USERNAME", "hanchae"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST") or env("DB_ADDRESS", "127.0.0.1"),
        "PORT": env("DB_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        "TEST": {
            "NAME": "test_hanchae",
            "CHARSET": "utf8mb4",
            "COLLATION": "utf8mb4_0900_as_ci",
        },
    }
}


# 회원
AUTH_USER_MODEL = "accounts.User"

# 비밀번호는 Argon2 로 해시한다 (ERD REQ-002)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# 화면에 보일 문장은 accounts/serializers.py 의 PASSWORD_MESSAGES 가 오류 코드마다 정한다
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ["email", "nickname"]},
    },
]
# 비밀번호 재설정 메일의 링크를 쓸 수 있는 시간 (초)
PASSWORD_RESET_TIMEOUT = 60 * 60

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# django-allauth: 아이디 없이 이메일로 로그인, 이메일 인증 필수 (AUTH-01)
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_UNIQUE_EMAIL = True
# 인증 메일의 링크를 프론트의 인증 화면(/verify-email)으로
ACCOUNT_ADAPTER = "apps.accounts.adapter.AccountAdapter"
# allauth 가 로그인 뒤 돌아갈 곳(next)이 없을 때
LOGIN_REDIRECT_URL = "/"
# 메일의 링크 · 소셜 로그인의 callback 주소를 사이트의 접속 방식으로 만든다 (제공사에 등록한 주소와 맞아야 한다)
ACCOUNT_DEFAULT_HTTP_PROTOCOL = SCHEME

# 소셜 로그인 (카카오 · 구글 · 네이버, AUTH-03). 앱 키를 넣은 제공사만 켜진다.
# 켜진 제공사의 /accounts/<제공사>/login/ 과 callback 만 열고(config/urls.py), 첫 가입의 닉네임 · 약관 동의는
# 로그인 화면이 받는다 (POST /api/auth/social/signup).
SOCIAL_PROVIDER_KEYS = {
    "kakao": ("KAKAO_CLIENT_ID", "KAKAO_SECRET"),  # REST API 키 · 보안의 Client Secret
    "google": ("GOOGLE_CLIENT_ID", "GOOGLE_SECRET"),
    "naver": ("NAVER_CLIENT_ID", "NAVER_SECRET"),
}
SOCIALACCOUNT_PROVIDERS = {
    provider: {"APPS": [{"client_id": env(id_name), "secret": env(secret_name, "")}]}
    for provider, (id_name, secret_name) in SOCIAL_PROVIDER_KEYS.items()
    if env(id_name)
}
if "google" in SOCIALACCOUNT_PROVIDERS:
    SOCIALACCOUNT_PROVIDERS["google"]["SCOPE"] = ["profile", "email"]
SOCIAL_PROVIDERS = list(SOCIALACCOUNT_PROVIDERS)
SOCIALACCOUNT_ADAPTER = "apps.accounts.adapter.SocialAccountAdapter"
SOCIALACCOUNT_QUERY_EMAIL = True
# 제공사가 본인을 확인했으므로 메일 인증을 따로 받지 않는다. 대신 제공사가 인증했다고 알려 준 이메일만 쓴다 (adapter.py)
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
# 제공사가 인증한 이메일이 한채에서도 인증을 마친 회원의 이메일이면 그 회원으로 로그인하고 계정을 잇는다
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_STORE_TOKENS = False

# allauth 의 EmailAddress 는 조건부 유일 제약을 쓰는데 MySQL 은 이를 지원하지 않는다.
# 같은 이메일 중복은 users.email 유일 제약과 ACCOUNT_UNIQUE_EMAIL 이 대신 막는다.
SILENCED_SYSTEM_CHECKS = ["models.W036"]

# 인증 메일 보내기. 한채 전용 Gmail 계정과 앱 비밀번호가 있으면 Gmail 로 보내고,
# 없으면(개발 중) 메일을 터미널에 찍는다. 받는 주소는 가입자가 적은 어떤 메일이든 된다.
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = True
    EMAIL_TIMEOUT = 15
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = f"한채 <{EMAIL_HOST_USER or 'noreply@localhost'}>"
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[한채] "


# 로그인 유지: 마지막 사용 기준 2주 (기능명세서 9.2)
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
if HANCHAE_DOMAIN:
    # 모든 한채 서브도메인에서 로그인이 이어지게 한다 (API 명세서 2.2)
    SESSION_COOKIE_DOMAIN = f".{HANCHAE_DOMAIN}"
    CSRF_COOKIE_DOMAIN = f".{HANCHAE_DOMAIN}"
    # http · https 둘 다 믿는다. USE_HTTPS 를 실제 접속 방식과 다르게 넣어도 모든 저장 요청이 403 으로 막히지 않게
    CSRF_TRUSTED_ORIGINS = [
        f"{scheme}://{host}" for scheme in ("https", "http") for host in (HANCHAE_DOMAIN, f"*.{HANCHAE_DOMAIN}")
    ]
    CORS_ALLOWED_ORIGIN_REGEXES = [rf"^{SCHEME}://([a-z0-9-]+\.)?{HANCHAE_DOMAIN.replace('.', r'\.')}$"]
else:
    CSRF_TRUSTED_ORIGINS = ["http://localhost:5500", "http://127.0.0.1:5500"]
    CORS_ALLOWED_ORIGIN_REGEXES = [r"^http://([a-z0-9-]+\.)?localhost(:\d+)?$", r"^http://127\.0\.0\.1(:\d+)?$"]
CORS_ALLOW_CREDENTIALS = True


# Django REST Framework (API 명세서 2장)
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "apps.common.errors.exception_handler",
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
    # 요청 횟수 제한: throttle_scope 를 정한 API 의 바꾸는 요청만 센다 (apps/common/throttles.py)
    # 회원은 회원마다, 비회원은 IP 마다. 학교처럼 여럿이 한 IP 를 함께 쓰는 곳을 생각해 넉넉히 둔다
    "DEFAULT_THROTTLE_CLASSES": ["apps.common.throttles.ScopedWriteThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "login": "30/min",  # 로그인 · 이메일 인증 (비밀번호를 확인하는 곳)
        "signup": "30/hour",
        "auth_mail": "20/hour",  # 인증 메일 다시 보내기 · 비밀번호 재설정 메일
        "password_reset": "30/hour",  # 새 비밀번호 정하기
        "post_publish": "30/hour",
        "image_upload": "120/hour",
        "comment": "10/min",
        "post_view": "300/hour",  # 기록 조회 수 세기 (부풀리기 막기. 넘으면 429 로 세지 않는다)
        "guestbook": "10/min",
    },
    # 손님의 IP 는 nginx 가 X-Forwarded-For 끝에 붙인 값을 쓴다 (앞쪽은 손님이 마음대로 적어 보낼 수 있다)
    # nginx 없이 바로 받는 곳(노트북의 docker compose · runserver)에는 이 헤더가 없어 접속 주소를 그대로 쓴다
    "NUM_PROXIES": int(env("NUM_PROXIES", "1")),
}

# 캐시: 요청 횟수 · 로그인 실패 횟수를 센다. gunicorn 작업자 · 컨테이너가 여럿이라 메모리가 아니라 DB 에 둔다.
# 테이블은 migrate 가 만든다 (accounts 0003)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_entries",
        "OPTIONS": {"MAX_ENTRIES": 20000},
    }
}


# 언어 · 시각: UTC 로 저장하고 화면에서 한국 시간으로 보여 준다 (ERD REQ-001)
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True


STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
# 운영에서 올린 이미지를 Django 가 직접 내보낼지. nginx 가 /media/ 를 맡으면 0 으로 둔다.
SERVE_MEDIA = env("SERVE_MEDIA", "1" if DEBUG else "0") == "1"
# 화면 파일(index.html · css · js)이 있는 폴더. 기본은 저장소 루트
FRONTEND_DIR = Path(env("FRONTEND_DIR", str(BASE_DIR.parent)))

# 이미지 업로드 상한 10MB (ERD REQ-004)
MAX_IMAGE_BYTES = 10 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# 운영 (nginx 뒤에서 gunicorn 으로 돈다)
USE_X_FORWARDED_HOST = True
# nginx 가 X-Forwarded-Proto 로 알려 주는 접속 방식을 믿는다 (https 로 들어온 요청을 https 로 알아보게)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if USE_HTTPS:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # 브라우저가 앞으로 이 사이트를 https 로만 열게 한다 (https 로 들어온 응답에만 붙는다).
    # http → https 넘기기(SECURE_SSL_REDIRECT)는 켜지 않는다: 배포의 상태 확인이 http://127.0.0.1 로 묻는다
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
