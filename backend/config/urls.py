from importlib import import_module

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic.base import RedirectView
from django.views.static import serve

from config.frontend import frontend

api_patterns = [
    path("", include("apps.accounts.urls")),
    path("", include("apps.blogs.urls")),
    path("", include("apps.posts.urls")),
    path("", include("apps.community.urls")),
    path("", include("apps.rankings.urls")),
    path("", include("apps.moderation.urls")),
]

urlpatterns = [
    path("api/", include(api_patterns)),
    path("django-admin/", admin.site.urls),
]


def social_login_patterns(providers):
    """소셜 로그인: 앱 키를 넣은 제공사의 /accounts/<제공사>/login/ 과 callback 만 연다.

    allauth 의 다른 화면(가입 · 로그인 · 비밀번호 · 계정 연결)은 열지 않는다. 열면 한채의 규칙
    (약관 동의, 인증할 때 비밀번호 확인, 요청 횟수 제한)을 건너뛰는 두 번째 입구가 된다.
    처음 온 사람은 allauth 가 socialaccount_signup 으로 보내고, 로그인 화면이 가입을 마무리한다.
    """
    patterns = [
        path("social/signup/", RedirectView.as_view(url="/login?social=signup"), name="socialaccount_signup"),
    ]
    for provider in providers:
        patterns += import_module(f"allauth.socialaccount.providers.{provider}.urls").urlpatterns
    return patterns


if settings.SOCIAL_PROVIDERS:
    urlpatterns += [path("accounts/", include(social_login_patterns(settings.SOCIAL_PROVIDERS)))]

if settings.SERVE_MEDIA:
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]

# 나머지 주소는 화면 파일. 위의 주소(끝 / 를 빠뜨린 경우 포함)는 가리지 않는다
urlpatterns += [re_path(r"^(?!api/|django-admin|accounts|media/)(?P<path>.*)$", frontend)]

# 없는 주소 · 서버 오류도 한채 모양으로 (DEBUG=0 일 때 쓰인다)
handler404 = "config.frontend.not_found"
handler500 = "config.frontend.server_error"
