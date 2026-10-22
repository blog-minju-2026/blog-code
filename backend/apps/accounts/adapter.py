"""django-allauth 동작을 한채에 맞춘다.

한채의 이메일 가입 · 로그인은 allauth 화면을 거치지 않는다 (views.py). allauth 는 소셜 로그인에서
제공사와 주고받는 일만 맡고, 그 결과는 모두 로그인 화면(/login?social=...)으로 돌려보낸다.
allauth 의 화면은 열지 않으므로(config/urls.py) 그쪽으로 보내는 곳은 여기서 모두 바꾼다.
"""

import logging

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.base import AuthError, AuthProcess
from django.http import HttpResponseRedirect

from apps.common.access import current_sanction

from .social import email_is_trusted, keep_only_signup_values

logger = logging.getLogger(__name__)

# 소셜 로그인을 이용 제한으로 막았을 때 사유 · 기한을 로그인 화면에 한 번 넘긴다 (GET /api/auth/social)
SOCIAL_BLOCKED_SESSION_KEY = "hanchae_social_blocked"


def social_result(state):
    """소셜 로그인의 결과를 알리는 로그인 화면. state: signup · cancelled · error · inactive · suspended"""
    return HttpResponseRedirect(f"/login?social={state}")


class AccountAdapter(DefaultAccountAdapter):
    def get_email_confirmation_url(self, request, emailconfirmation):
        """인증 메일의 링크를 프론트의 인증 화면(/verify-email)으로 보낸다 (API 명세서 7.2).

        그 화면이 POST /api/auth/email/verify 로 키를 보내 인증을 마친다.
        """
        return request.build_absolute_uri(f"/verify-email?key={emailconfirmation.key}")

    def get_password_reset_url(self, request, uid, token):
        """비밀번호 재설정 메일의 링크. 프론트의 화면(/reset-password)이 새 비밀번호와 함께
        POST /api/auth/password/reset/confirm 으로 보낸다."""
        return request.build_absolute_uri(f"/reset-password?uid={uid}&token={token}")

    def pre_login(self, request, user, **kwargs):
        """소셜 로그인도 이메일 로그인(LoginView)처럼 탈퇴 · 이용 제한 회원을 들이지 않는다.

        이메일 로그인은 allauth 를 거치지 않으므로 여기는 소셜 로그인에만 쓰인다.
        """
        if not user.is_active:
            return social_result("inactive")
        sanction = current_sanction(user)
        if sanction is not None:
            request.session[SOCIAL_BLOCKED_SESSION_KEY] = {
                "reason": sanction.reason,
                "ends_at": sanction.ends_at.isoformat() if sanction.ends_at else None,
            }
            return social_result("suspended")
        return None

    def add_message(self, *args, **kwargs):
        """allauth 의 안내 문장('로그인했어요' 등)은 한채 화면에 보이지 않으므로 쌓지 않는다."""


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_auto_signup_allowed(self, request, sociallogin):
        """처음 온 사람은 늘 가입 마무리(닉네임 · 약관 동의)를 거친다 (POST /api/auth/social/signup)."""
        return False

    def populate_user(self, request, sociallogin, data):
        """제공사가 준 이름 · 이메일을 회원에 바로 넣지 않는다. 가입 마무리에서 정한다."""
        return sociallogin.user

    def authenticate_by_email(self, sociallogin):
        """제공사가 인증한 이메일이, 한채에서도 인증을 마친 이메일일 때만 그 회원으로 로그인한다.

        인증을 기다리는 가입은 남이 먼저 적어 둔 주소일 수 있어 잇지 않는다
        (그런 가입은 가입 마무리에서 자리를 내준다). 이메일 확인 여부를 알려 주지 않는 제공사(네이버)는 잇지 않는다.
        """
        if not email_is_trusted(sociallogin):
            return None
        for address in sociallogin.email_addresses:
            if not address.verified:
                continue
            local = (
                EmailAddress.objects.select_related("user").filter(email__iexact=address.email, verified=True).first()
            )
            if local is not None:
                return local.user, local.email
        return None

    def pre_social_login(self, request, sociallogin):
        """로그인만 받는다. 계정 연결(connect)은 화면이 없어 열지 않는다.

        처음 온 사람은 가입을 마무리할 때까지 세션에 머물므로, 프로필 원본을 미리 줄여 둔다.
        """
        if sociallogin.state.get("process", AuthProcess.LOGIN) != AuthProcess.LOGIN:
            raise ImmediateHttpResponse(social_result("error"))
        if not sociallogin.is_existing:
            keep_only_signup_values(sociallogin)

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        """제공사에서 취소하거나 실패하면 allauth 의 오류 화면 대신 로그인 화면으로."""
        if error == AuthError.CANCELLED:
            raise ImmediateHttpResponse(social_result("cancelled"))
        logger.warning("소셜 로그인 실패: %s %s %r", getattr(provider, "id", provider), error, exception)
        raise ImmediateHttpResponse(social_result("error"))
