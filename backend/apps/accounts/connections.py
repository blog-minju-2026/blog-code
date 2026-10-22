"""소셜 계정 연동 (AUTH-07): 로그인한 회원이 카카오 · 구글 · 네이버 계정을 자기 한채 계정에 잇고 끊는다.

흐름
1. 내 정보에서 「연결하기」 → POST /api/me/social/connect 로 비밀번호(없으면 닉네임)를 확인하고, 세션에 '이 제공사를
   잠깐 이어도 된다'는 표시(CONNECT_SESSION_KEY)를 남긴다
2. 화면이 allauth 의 /accounts/<제공사>/login/ 으로 process=connect 를 보내 제공사 로그인을 거친다
3. 돌아오면 어댑터(adapter.py 의 pre_social_login)가 표시를 확인 · 소모하고, 다른 한채 계정에 이미 이어진
   소셜 계정이면 거절한다. 결과는 /me?connect=done|taken|already|error&provider=… 로 알린다

규칙
- 한 소셜 계정은 한채 계정 하나에만, 한 한채 계정에는 제공사마다 하나만 잇는다
- 마지막 남은 로그인 방법(비밀번호가 없고 다른 소셜 연결도 없을 때)은 끊을 수 없다
"""

import time

from allauth.socialaccount.models import SocialAccount
from django.conf import settings

from .social import PROVIDER_NAMES

CONNECT_SESSION_KEY = "hanchae_social_connect"
# 비밀번호를 확인한 뒤 제공사 로그인을 마치기까지 기다리는 시간 (초)
CONNECT_WINDOW = 10 * 60


def allow_connect(request, provider):
    request.session[CONNECT_SESSION_KEY] = {"provider": provider, "at": time.time()}


def take_connect_allowance(request, provider):
    """표시가 있고 그 제공사 · 시간 안이면 True. 한 번 쓰면 지운다."""
    allowance = request.session.pop(CONNECT_SESSION_KEY, None)
    return bool(
        allowance
        and allowance.get("provider") == provider
        and time.time() - allowance.get("at", 0) <= CONNECT_WINDOW
    )


def can_disconnect(user, account, accounts=None):
    """끊어도 로그인할 방법이 남는지: 비밀번호가 있거나, 다른 소셜 연결이 있으면."""
    accounts = accounts if accounts is not None else list(SocialAccount.objects.filter(user=user))
    return user.has_usable_password() or any(a.pk != account.pk for a in accounts)


def login_methods(user):
    """GET /api/me/login-methods 의 내용."""
    accounts = list(SocialAccount.objects.filter(user=user))
    by_provider = {a.provider: a for a in accounts}
    # 켜진 제공사, 그리고 지금은 꺼졌어도 이미 이어 둔 제공사
    providers = list(settings.SOCIAL_PROVIDERS) + [p for p in by_provider if p not in settings.SOCIAL_PROVIDERS]
    return {
        "email": user.email,
        "has_password": user.has_usable_password(),
        "confirm_with": "password" if user.has_usable_password() else "nickname",
        "nickname": user.nickname,
        "providers": [
            {
                "provider": provider,
                "name": PROVIDER_NAMES.get(provider, provider),
                "enabled": provider in settings.SOCIAL_PROVIDERS,
                "connected": provider in by_provider,
                "connected_at": by_provider[provider].date_joined if provider in by_provider else None,
                "can_disconnect": provider in by_provider and can_disconnect(user, by_provider[provider], accounts),
            }
            for provider in providers
        ],
    }
