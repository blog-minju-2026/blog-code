"""요청마다 하는 일: 이용 제한된 회원 막기, 세션 저장 줄이기, 보안 헤더(CSP)."""

from django.contrib.auth import logout
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import JsonResponse

from .access import current_sanction

# 로그인 상태가 뜻이 있는 주소. 나머지(/, /login, /css/…, /js/…, /media/…)는 누구에게나 같은 화면 파일이다
MEMBER_PATHS = ("/api/", "/accounts/", "/django-admin/")


def is_screen_file(request):
    return not request.path.startswith(MEMBER_PATHS)


class QuietSessionMiddleware(SessionMiddleware):
    """세션을 읽지 않은 요청은 세션을 다시 저장하지 않는다.

    SESSION_SAVE_EVERY_REQUEST 는 '쓰는 동안은 로그인을 이어 준다'는 뜻인데, Django 는 세션을 읽지도 않은 요청
    (화면 파일 · css · js · 사진)까지 요청마다 세션을 DB 에서 읽고 다시 쓴다. 화면 하나를 열면 파일이 열 개쯤 나가므로
    로그인한 사람은 화면마다 DB 를 스무 번쯤 더 쓰게 된다. 화면은 열릴 때마다 /api/auth/me 를 부르므로 로그인은 그 요청이 이어 준다.
    """

    def process_response(self, request, response):
        session = getattr(request, "session", None)
        if session is not None and not session.accessed and not session.modified:
            return response
        return super().process_response(request, response)


# 이 사이트가 불러와도 되는 것 (XSS 가 뚫렸을 때의 두 번째 방어선. 본문 HTML 은 서버 · 화면이 이미 한 번씩 거른다)
# - script: 우리 파일만. 화면에 끼어든 <script> · onclick 같은 인라인 코드는 실행되지 않는다
# - style: 우리 파일 + 글꼴 CSS(jsdelivr 의 Pretendard, Google Fonts). 'unsafe-inline' 은 본문의 글자색 · 정렬(style 속성) 때문에 둔다
# - img: 우리 서버에 올린 사진과 data: (CSS 안의 작은 그림)
# - form-action 은 두지 않는다: 소셜 로그인이 /accounts/<제공사>/login/ 으로 보낸 폼을 제공사 주소로 넘기는데, 브라우저가 그 넘김도 막는다
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
        "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
    ]
)


class ContentSecurityPolicyMiddleware:
    """모든 응답에 Content-Security-Policy 를 붙인다. Django 운영 화면(/django-admin/)은 뺀다 (그 화면의 인라인 코드가 막힌다)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/django-admin/") and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        return response


class SuspendedUserMiddleware:
    """제한 중이면 세션을 끊는다. API 요청에는 사유 · 기한을 담아 403 SUSPENDED 로 한 번 답한다.
    다음 요청부터는 비회원이다. 화면 파일 요청은 보지 않는다 (누구에게나 같은 파일이고, 화면이 여는 즉시 API 를 부른다)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 화면 파일 요청은 건너뛴다 (세션 · 회원 · 제한 기록을 읽지 않는다). 화면이 곧바로 부르는 API 요청에서 막는다
        if is_screen_file(request):
            return self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            sanction = current_sanction(user)
            if sanction is not None:
                logout(request)
                if request.path.startswith("/api/"):
                    return JsonResponse(
                        {
                            "error": {
                                "code": "SUSPENDED",
                                "message": "이용이 제한된 계정이에요.",
                                "detail": {"reason": sanction.reason, "ends_at": sanction.ends_at},
                            }
                        },
                        status=403,
                        json_dumps_params={"ensure_ascii": False},
                    )
        return self.get_response(request)
