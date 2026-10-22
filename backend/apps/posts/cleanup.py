"""쓰이지 않는 사진 정리 (ERD REQ-004).

글쓰기 화면에서 올렸다가 발행하지 않았거나, 기록을 지우거나 고치며 본문에서 빠진 사진은 images 에만 남는다.
올린 지 하루가 지나도 어디에도 쓰이지 않으면 행과 파일(원본 · 목록용)을 지운다.
쓰이는 곳: 기록 본문(post_images), 대표 · 첫 이미지, 회원 프로필 사진, 한채 사진 (프로필 · 한채 사진은 파일 경로로 가리킨다).
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.accounts.models import User
from apps.blogs.models import Blog
from apps.common.storage import delete_files

from .models import Image, Post, PostImage

UNUSED_AFTER = timedelta(hours=24)


def unused_images(now=None):
    cutoff = (now or timezone.now()) - UNUSED_AFTER
    profile_files = set(User.objects.exclude(profile_image="").exclude(profile_image__isnull=True).values_list("profile_image", flat=True))
    profile_files |= set(Blog.objects.exclude(profile_image="").exclude(profile_image__isnull=True).values_list("profile_image", flat=True))
    return (
        Image.objects.filter(created_at__lt=cutoff)
        .filter(~Exists(PostImage.objects.filter(image=OuterRef("pk"))))
        .filter(~Exists(Post.objects.filter(Q(cover_image=OuterRef("pk")) | Q(first_image=OuterRef("pk")))))
        .exclude(file__in=profile_files)
    )


def delete_unused_images(now=None, dry_run=False):
    """지운(지울) 사진 수를 돌려준다."""
    images = list(unused_images(now))
    if dry_run or not images:
        return len(images)
    files = [name for image in images for name in (image.file.name, image.thumb_file.name)]
    with transaction.atomic():
        Image.objects.filter(pk__in=[image.pk for image in images]).delete()
        transaction.on_commit(lambda: delete_files(files))
    return len(images)
