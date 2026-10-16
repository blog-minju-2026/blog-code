"""인증을 안 마친 이메일 가입 (인증 대기).

가입하면 users 행부터 만들고 인증 메일을 보낸다. 링크를 누르기 전까지는 로그인할 수 없어 회원이 아니다.
이메일을 잘못 쓴 가입은 끝내 인증되지 않으므로, 회원 목록에서 빼고 닉네임 · 이메일 자리를 내준다.
"""

from datetime import timedelta

from allauth.account import app_settings
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.moderation.models import UserSanction

from .models import User, VerificationMailLog


def pending_signups(qs=None):
    """이메일이 있는데 하나도 인증하지 않은 이메일 가입 회원 (소셜 가입은 빼고)."""
    qs = User.objects.all() if qs is None else qs
    return qs.filter(
        Exists(EmailAddress.objects.filter(user=OuterRef("pk"))),
        ~Exists(EmailAddress.objects.filter(user=OuterRef("pk"), verified=True)),
        ~Exists(SocialAccount.objects.filter(user=OuterRef("pk"))),
    )


def removable_pending_signups():
    """지워도 되는 인증 대기 가입. 이용 제한 기록이 걸려 있으면 남긴다 (PROTECT)."""
    return pending_signups().filter(~Exists(UserSanction.objects.filter(user=OuterRef("pk"))))


def expired_pending_signups(now=None):
    """마지막으로 보낸 인증 링크까지 만료된 인증 대기 가입 (지워도 되는 것만)."""
    cutoff = (now or timezone.now()) - timedelta(days=app_settings.EMAIL_CONFIRMATION_EXPIRE_DAYS)
    recent_mail = VerificationMailLog.objects.filter(email__iexact=OuterRef("email"), last_sent_at__gte=cutoff)
    return removable_pending_signups().filter(created_at__lt=cutoff).filter(~Exists(recent_mail))
