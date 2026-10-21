"""소셜 로그인으로 막 돌아온 사람의 값 (가입 마무리에 쓴다, AUTH-03).

제공사가 돌려준 프로필 원본(extra_data)은 남기지 않는다. 한채는 provider · uid 로 회원을 찾고,
이메일은 account_emailaddress 에 따로 둔다. 가입을 마무리하는 동안 세션에는 닉네임 칸에 미리 채울 별명만 둔다.
"""

from allauth.socialaccount.models import SocialAccount
from django.db.models.signals import pre_save
from django.dispatch import receiver

PROVIDER_NAMES = {"kakao": "카카오", "google": "구글", "naver": "네이버"}


def verified_email(sociallogin):
    """제공사가 인증했다고 알려 준 이메일(소문자). 없으면 None.

    카카오는 비즈 앱이 아니면 이메일을 주지 않는다. 그런 회원은 이메일 없이 가입한다.
    """
    for address in sociallogin.email_addresses:
        if address.verified and address.email:
            return address.email.strip().lower()
    return None


def provider_nickname(provider, data):
    """제공사 프로필 원본에서 이름 · 별명을 꺼낸다."""
    if provider == "kakao":
        name = (data.get("kakao_account") or {}).get("profile", {}).get("nickname") or (
            data.get("properties") or {}
        ).get("nickname")
    elif provider == "naver":
        name = data.get("nickname") or data.get("name")
    else:
        name = data.get("name")
    return (name or "").strip()


def keep_only_signup_values(sociallogin):
    """처음 온 사람의 프로필 원본에서 가입 마무리에 쓰는 별명만 남긴다 (세션에 담기기 전에)."""
    account = sociallogin.account
    account.extra_data = {"nickname": provider_nickname(account.provider, account.extra_data or {})}


def suggested_nickname(sociallogin):
    """제공사의 이름 · 별명. 가입 마무리의 닉네임 칸에 미리 채운다 (바꿀 수 있다)."""
    name = ((sociallogin.account.extra_data or {}).get("nickname") or "").strip()[:20]
    return name if len(name) >= 2 else ""


@receiver(pre_save, sender=SocialAccount)
def drop_provider_profile(sender, instance, **kwargs):
    """소셜 계정을 저장할 때마다 프로필 원본을 비운다. allauth 는 로그인할 때마다 새 원본으로 덮어쓴다."""
    instance.extra_data = {}


def pending_signup_payload(sociallogin):
    return {
        "provider": sociallogin.account.provider,
        "provider_name": PROVIDER_NAMES.get(sociallogin.account.provider, sociallogin.account.provider),
        "email": verified_email(sociallogin),
        "nickname": suggested_nickname(sociallogin),
    }
