from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
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

# 소셜 로그인(카카오 · 구글 · 네이버)은 제공사 앱 키를 등록한 뒤 SOCIAL_LOGIN=1 로 켠다.
# 켜기 전에는 allauth 화면(/accounts/...)을 열지 않는다. 열어 두면 버튼이 500 을 내고,
# allauth 의 기본 가입 · 로그인 화면이 한채의 규칙(약관 동의, 이용 제한 검사)을 건너뛴다.
if settings.SOCIAL_LOGIN:
    urlpatterns += [path("accounts/", include("allauth.urls"))]

if settings.SERVE_MEDIA:
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]

# 나머지 주소는 화면 파일. 위의 주소(끝 / 를 빠뜨린 경우 포함)는 가리지 않는다
urlpatterns += [re_path(r"^(?!api/|django-admin|accounts|media/)(?P<path>.*)$", frontend)]

# 없는 주소 · 서버 오류도 한채 모양으로 (DEBUG=0 일 때 쓰인다)
handler404 = "config.frontend.not_found"
handler500 = "config.frontend.server_error"
