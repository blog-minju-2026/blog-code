"""한채 허물기 (BLOG-04 · 탈퇴 공용): 한채 안의 것을 지우고, 한채 행은 '허문 한채'로 남겨 주소를 영구히 예약한다.

- 지운다: 기록(임시저장 포함, 딸린 댓글 · 공감 · 조회 · 순위가 함께), 그 기록의 사진(파일까지), 방, 태그,
  받은 방명록, 이 한채의 이웃, 한채 사진
- 남긴다: 주인의 계정, 주인이 다른 한채에 남긴 것, 주인이 맺은 이웃 · 누른 공감 (탈퇴는 withdrawal.py 가 따로 지운다)
- 한채 행은 남겨 주소를 막아 둔다 (남이 같은 주소로 그 한채인 척하지 못하게). 주인은 다른 주소로 새 한채를 지을 수 있다
"""

from django.db.models import Q
from django.utils import timezone

from apps.community.models import GuestbookEntry, Subscription
from apps.posts.models import Category, Image, Post, Tag

from .models import Blog

DEMOLISHED_BLOG_NAME = "허문 한채"


def demolish_summary(blog):
    """허물기 확인 창에 보일 수."""
    posts = Post.objects.filter(blog=blog)
    return {
        "name": blog.name,
        "address": blog.address,
        "post_count": posts.filter(status=Post.Status.PUBLISHED).count(),
        "draft_count": posts.filter(status=Post.Status.DRAFT).count(),
        "room_count": Category.objects.filter(blog=blog).count(),
        "guestbook_count": GuestbookEntry.objects.filter(blog=blog).count(),
        "subscriber_count": Subscription.objects.filter(blog=blog).count(),
    }


def demolish_blogs(blogs, owner):
    """blogs 를 허문다. 호출하는 쪽이 트랜잭션을 열고, 돌려준 파일 이름은 DB 가 확정된 뒤 지운다."""
    blogs = list(blogs)
    files = [b.profile_image.name for b in blogs if b.profile_image]

    # 그 기록들에 쓴 사진 (주인의 프로필 사진으로도 쓰는 파일은 남긴다)
    keep = {owner.profile_image.name} if owner.profile_image else set()
    images = Image.objects.filter(
        Q(post_images__post__blog__in=blogs)
        | Q(pk__in=Post.objects.filter(blog__in=blogs, cover_image__isnull=False).values("cover_image"))
    ).distinct()
    images = [img for img in images if img.file.name not in keep]
    for image in images:
        files += [name for name in (image.file.name, image.thumb_file.name) if name]

    Post.objects.filter(blog__in=blogs).delete()
    Image.objects.filter(pk__in=[img.pk for img in images]).delete()
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
    return files
