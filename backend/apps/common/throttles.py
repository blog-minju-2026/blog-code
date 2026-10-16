"""요청 횟수 제한 (남용 막기).

API 마다 throttle_scope 를 정하면 그 API 의 바꾸는 요청(POST · PATCH · PUT · DELETE)만 센다.
회원은 회원마다, 비회원은 IP 마다 센다. 횟수는 settings.REST_FRAMEWORK 의 DEFAULT_THROTTLE_RATES 에 있다.
넘으면 429 TOO_MANY_REQUESTS (apps/common/errors.py).
"""

from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import ScopedRateThrottle


class ScopedWriteThrottle(ScopedRateThrottle):
    def allow_request(self, request, view):
        # 같은 주소의 목록 보기(GET)는 세지 않는다. 예: 댓글 목록 · 쓰기가 한 주소
        if request.method in SAFE_METHODS:
            return True
        return super().allow_request(request, view)
