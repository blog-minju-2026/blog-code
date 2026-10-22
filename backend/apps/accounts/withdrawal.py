"""회원 탈퇴 (AUTH-06).

다른 한채에 남긴 댓글 · 방명록은 작성자를 지울 수 없게 잡고 있다(PROTECT). 그래서 회원 행은 남기되
알아볼 수 있는 값을 모두 비우고 is_active=False 로 둔다. 화면은 그런 회원을 '떠난 사람'으로 보인다.

- 지운다: 내 한채의 기록 · 방 · 태그 · 받은 방명록 · 이웃, 올린 사진(파일까지), 내가 맺은 이웃 · 누른 공감,
  이메일 인증 · 소셜 계정 연결, 내 정보(이메일 · 닉네임 · 사진 · 비밀번호)
- 남긴다: 다른 한채에 남긴 댓글 · 방명록('떠난 사람'), 이용 제한 기록
- 한채 행은 '허문 한채'로 남겨 주소를 영구히 예약한다 (남이 같은 주소로 내 한채인 척하지 못하게)
"""

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from apps.blogs.models import Blog
from apps.community.models import Comment, GuestbookEntry, PostLike, Subscription
from apps.posts.models import Category, Image, Post, Tag

from . import attempts
from .models import VerificationMailLog
from .social import PROVIDER_NAMES

# 탈퇴한 회원의 한채 이름 (행은 주소를 예약하려고 남긴다)
DEMOLISHED_BLOG_NAME = "허문 한채"


def leave_summary(user):
    """탈퇴 확인 창에 보일 것: 사라지는 것 · 남는 것의 수와, 무엇으로 본인을 확인할지."""
    blog = user.blogs.filter(deleted_at__isnull=True).first()
    social = SocialAccount.objects.filter(user=user).values_list("provider", flat=True).first()
    return {
        "nickname": user.nickname,
        # 비밀번호가 있으면 비밀번호로, 없으면(소셜로만 가입) 닉네임을 적어 확인한다
        "confirm_with": "password" if user.has_usable_password() else "nickname",
        "social_provider": PROVIDER_NAMES.get(social) if social else None,
        "blog": {"name": blog.name, "address": blog.address} if blog else None,
        "post_count": Post.objects.filter(blog__owner=user).count(),
        "subscriber_count": Subscription.objects.filter(blog=blog).count() if blog else 0,
        "comment_count": Comment.objects.filter(author=user).exclude(post__blog__owner=user).count(),
        "guestbook_count": GuestbookEntry.objects.filter(author=user).exclude(blog__owner=user).count(),
    }


def _file_names(*fields):
    return [f.name for f in fields if f]


def withdraw(user):
    """회원을 탈퇴시킨다. 세션은 부르는 쪽(LeaveView)이 끊는다."""
    files = _file_names(user.profile_image)
    with transaction.atomic():
        blogs = list(Blog.objects.select_for_update().filter(owner=user))
        for blog in blogs:
            files += _file_names(blog.profile_image)
        # 내 한채 안의 것: 기록(딸린 댓글 · 공감 · 조회 · 순위가 함께), 방, 태그, 받은 방명록, 이웃
        Post.objects.filter(blog__in=blogs).delete()
        # 방은 상위 방을 PROTECT 로 잡으므로 아래 방부터 지운다
        rooms = Category.objects.filter(blog__in=blogs)
        while rooms.exists():
            rooms.filter(children__isnull=True).delete()
        Tag.objects.filter(blog__in=blogs).delete()
        GuestbookEntry.objects.filter(blog__in=blogs).delete()
        Subscription.objects.filter(blog__in=blogs).delete()
        now = timezone.now()
        Blog.objects.filter(pk__in=[b.pk for b in blogs]).update(
            name=DEMOLISHED_BLOG_NAME, description="", profile_image=None, deleted_at=now, updated_at=now
        )

        # 내가 한 것: 올린 사진, 맺은 이웃, 누른 공감
        for image in Image.objects.filter(uploader=user):
            files += _file_names(image.file, image.thumb_file)
        Image.objects.filter(uploader=user).delete()
        Subscription.objects.filter(subscriber=user).delete()
        PostLike.objects.filter(user=user).delete()

        # 로그인 수단과 내 정보
        if user.email:
            VerificationMailLog.objects.filter(email__iexact=user.email).delete()
            attempts.clear(user.email)
        EmailAddress.objects.filter(user=user).delete()
        SocialAccount.objects.filter(user=user).delete()
        user.email = None
        user.nickname = None
        user.profile_image = None
        user.set_unusable_password()  # 다른 기기의 로그인도 끊긴다 (세션이 비밀번호 해시를 확인한다)
        user.is_active = False
        user.is_staff = False
        user.is_superuser = False
        user.withdrawn_at = now
        user.save()

        # 파일은 DB 가 확정된 뒤에 지운다 (되돌려지면 파일은 남아 있어야 한다)
        transaction.on_commit(lambda: _delete_files(files))


def _delete_files(names):
    for name in names:
        try:
            default_storage.delete(name)
        except OSError:
            pass
