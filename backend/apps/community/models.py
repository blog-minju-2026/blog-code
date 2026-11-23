from django.conf import settings
from django.db import models


class HideableText(models.Model):
    """댓글과 방명록이 함께 쓰는 필드: 1~1,000자 순수 텍스트, 관리자 숨김, 등록 중복 방지 (REQ-009)."""

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="작성 회원"
    )
    content = models.TextField("내용", max_length=1000)
    edited_at = models.DateTimeField("수정 시각", null=True, blank=True)
    hidden_at = models.DateTimeField("관리자 숨김 시각", null=True, blank=True)
    hidden_reason = models.CharField("숨김 사유", max_length=200, null=True, blank=True)
    hidden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="숨긴 관리자",
    )
    client_token = models.CharField("등록 중복 방지 토큰", max_length=36, null=True, blank=True)
    created_at = models.DateTimeField("생성 일시", auto_now_add=True)
    updated_at = models.DateTimeField("수정 일시", auto_now=True)

    class Meta:
        abstract = True


class Comment(HideableText):
    """댓글 (ERD comments)."""

    post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="comments", verbose_name="기록")

    class Meta:
        db_table = "comments"
        ordering = ["created_at", "id"]
        verbose_name = "댓글"
        verbose_name_plural = "댓글"
        constraints = [
            models.UniqueConstraint(fields=["author", "client_token"], name="uk_comments_client_token"),
            models.CheckConstraint(
                condition=models.Q(hidden_at__isnull=True) | models.Q(hidden_reason__isnull=False),
                name="ck_comments_hidden_reason",
            ),
        ]


class GuestbookEntry(HideableText):
    """방명록 (ERD guestbook_entries). 특정 기록이 아니라 한채에 남긴다."""

    blog = models.ForeignKey(
        "blogs.Blog", on_delete=models.CASCADE, related_name="guestbook_entries", verbose_name="한채"
    )

    class Meta:
        db_table = "guestbook_entries"
        ordering = ["-created_at", "-id"]
        verbose_name = "방명록"
        verbose_name_plural = "방명록"
        constraints = [
            models.UniqueConstraint(fields=["author", "client_token"], name="uk_guestbook_client_token"),
            models.CheckConstraint(
                condition=models.Q(hidden_at__isnull=True) | models.Q(hidden_reason__isnull=False),
                name="ck_guestbook_entries_hidden_reason",
            ),
        ]


class PostLike(models.Model):
    """공감 (ERD post_likes, REQ-010). 회원은 글마다 한 번. 자기 글에는 공감할 수 없다(앱에서 검사)."""

    post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="likes", verbose_name="기록")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="post_likes", verbose_name="회원"
    )
    created_at = models.DateTimeField("생성 일시", auto_now_add=True)

    class Meta:
        db_table = "post_likes"
        verbose_name = "공감"
        verbose_name_plural = "공감"
        constraints = [
            models.UniqueConstraint(fields=["user", "post"], name="uk_post_likes"),
        ]


class Subscription(models.Model):
    """이웃 (ERD subscriptions, REQ-011). 자기 한채와는 이웃을 맺을 수 없다(앱에서 검사)."""

    blog = models.ForeignKey(
        "blogs.Blog", on_delete=models.CASCADE, related_name="subscriptions", verbose_name="이웃 맺은 한채"
    )
    subscriber = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions", verbose_name="이웃 맺은 회원"
    )
    created_at = models.DateTimeField("생성 일시", auto_now_add=True)

    class Meta:
        db_table = "subscriptions"
        verbose_name = "이웃"
        verbose_name_plural = "이웃"
        constraints = [
            models.UniqueConstraint(fields=["subscriber", "blog"], name="uk_subscriptions"),
        ]


class BlockedNeighbor(models.Model):
    """내보낸 이웃 (SUB-04). 주인이 내보낸 회원은 그 한채와 다시 이웃을 맺을 수 없다 (주인이 다시 받아 줄 때까지).

    이웃 공개 기록은 '이웃 맺기'를 누른 사람 모두가 본다. 주인이 그 범위를 정할 수 있게 하려는 것이다.
    """

    blog = models.ForeignKey(
        "blogs.Blog", on_delete=models.CASCADE, related_name="blocked_neighbors", verbose_name="한채"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+", verbose_name="내보낸 회원"
    )
    created_at = models.DateTimeField("내보낸 시각", auto_now_add=True)

    class Meta:
        db_table = "blog_blocked_neighbors"
        verbose_name = "내보낸 이웃"
        verbose_name_plural = "내보낸 이웃"
        constraints = [
            models.UniqueConstraint(fields=["blog", "user"], name="uk_blog_blocked_neighbors"),
        ]
