from django.conf import settings
from django.db import models


class UserSanction(models.Model):
    """회원 이용 제한 (ERD user_sanctions, REQ-012). ends_at 이 비어 있으면 영구 제한."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sanctions", verbose_name="대상 회원"
    )
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="처리한 관리자"
    )
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="해제한 관리자",
    )
    reason = models.CharField("사유", max_length=500)
    starts_at = models.DateTimeField("시작")
    ends_at = models.DateTimeField("끝", null=True, blank=True)
    released_at = models.DateTimeField("기한 전 해제 시각", null=True, blank=True)
    created_at = models.DateTimeField("생성 일시", auto_now_add=True)

    class Meta:
        db_table = "user_sanctions"
        verbose_name = "이용 제한"
        verbose_name_plural = "이용 제한"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=models.F("starts_at")),
                name="ck_user_sanctions_period",
            ),
        ]


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("관리 기록은 고칠 수 없어요.")

    def delete(self):
        raise PermissionError("관리 기록은 지울 수 없어요.")


class AdminLog(models.Model):
    """관리 기록 (ERD admin_logs, ADMIN-06). 추가만 하고 고치거나 지우지 않는다."""

    class Action(models.TextChoices):
        HIDE_POST = "HIDE_POST"
        UNHIDE_POST = "UNHIDE_POST"
        HIDE_COMMENT = "HIDE_COMMENT"
        UNHIDE_COMMENT = "UNHIDE_COMMENT"
        HIDE_GUESTBOOK = "HIDE_GUESTBOOK"
        UNHIDE_GUESTBOOK = "UNHIDE_GUESTBOOK"
        SANCTION_USER = "SANCTION_USER"
        RELEASE_USER = "RELEASE_USER"

    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="처리한 관리자"
    )
    action = models.CharField("동작", max_length=30)
    target_type = models.CharField("대상 종류", max_length=20)
    target_id = models.BigIntegerField("대상 ID")
    reason = models.CharField("사유", max_length=500)
    created_at = models.DateTimeField("생성 일시", auto_now_add=True)

    class Meta:
        db_table = "admin_logs"
        ordering = ["-created_at"]
        verbose_name = "관리 기록"
        verbose_name_plural = "관리 기록"

    objects = AppendOnlyQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("관리 기록은 고칠 수 없어요.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("관리 기록은 지울 수 없어요.")
