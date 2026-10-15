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

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
]

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
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
# 소셜 로그인을 켤지. 제공사 앱 키를 Django 운영 화면의 Social applications 에 등록한 뒤 1 로 (config/urls.py)
SOCIAL_LOGIN = env("SOCIAL_LOGIN", "0") == "1"
# 인증 메일의 링크를 프론트의 인증 화면(/verify-email)으로
ACCOUNT_ADAPTER = "apps.accounts.adapter.AccountAdapter"

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

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
