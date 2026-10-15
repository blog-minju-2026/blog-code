"""로그인한 채로 이용 제한된 회원을 다음 요청부터 막는다 (data-model 6절, ADMIN-02)."""

from django.contrib.auth import logout
from django.http import JsonResponse

from .access import current_sanction


class SuspendedUserMiddleware:
    """제한 중이면 세션을 끊는다. API 요청에는 사유 · 기한을 담아 403 SUSPENDED 로 한 번 답하고,
    화면 요청은 비회원으로 그대로 보여 준다. 다음 요청부터는 비회원이다."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
