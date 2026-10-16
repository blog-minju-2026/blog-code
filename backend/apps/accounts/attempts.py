"""비밀번호를 거듭 틀리면 그 이메일로는 잠시 비밀번호 확인을 막는다 (무차별 대입 막기).

IP 마다의 횟수 제한(settings 의 DEFAULT_THROTTLE_RATES)만으로는 여러 IP 에서 한 계정을 노리는 시도를 막지 못해
이메일마다 따로 센다. 로그인과 이메일 인증(가입할 때 정한 비밀번호를 확인한다)이 같은 횟수를 쓴다.
"""

import hashlib
import math
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.common.errors import APIError

FAILURE_LIMIT = 10
LOCK_WINDOW = timedelta(minutes=15)


def _key(email):
    return "password-failures:" + hashlib.sha256(email.strip().lower().encode()).hexdigest()


def ensure_not_locked(email):
    """처음 틀린 때부터 LOCK_WINDOW 안에 FAILURE_LIMIT 번 틀렸으면 429. 맞는 비밀번호도 받지 않는다."""
    state = cache.get(_key(email))
    if state and state["count"] >= FAILURE_LIMIT:
        seconds = max(1, math.ceil((state["until"] - timezone.now()).total_seconds()))
        raise APIError(
            429,
            "TOO_MANY_REQUESTS",
            f"비밀번호를 여러 번 틀렸어요. {math.ceil(seconds / 60)}분 뒤에 다시 시도해 주세요.",
            detail={"retry_after": seconds},
        )


def record_failure(email):
    key, now = _key(email), timezone.now()
    state = cache.get(key) or {"count": 0, "until": now + LOCK_WINDOW}
    state["count"] += 1
    cache.set(key, state, max(1, math.ceil((state["until"] - now).total_seconds())))


def clear(email):
    cache.delete(_key(email))
