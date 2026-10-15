"""숨김 · 이용 제한 처리 (ADMIN-02 · 03).

처리와 관리 기록(admin_logs)은 같은 트랜잭션에서 남긴다 (data-model 6절, review H-03).
"""

from django.db import transaction
from django.utils import timezone

from apps.common.access import current_sanction
from apps.common.errors import APIError

from .models import AdminLog, UserSanction

# 숨길 수 있는 것: 관리 기록의 target_type 과 동작 이름
HIDE_TARGETS = {
    "post": ("HIDE_POST", "UNHIDE_POST"),
    "comment": ("HIDE_COMMENT", "UNHIDE_COMMENT"),
    "guestbook": ("HIDE_GUESTBOOK", "UNHIDE_GUESTBOOK"),
}


def log(admin, action, target_type, target_id, reason):
    AdminLog.objects.create(admin=admin, action=action, target_type=target_type, target_id=target_id, reason=reason)


@transaction.atomic
def hide(item, target_type, admin, reason):
    """기록 · 댓글 · 방명록을 숨긴다. 이미 숨겨져 있으면 409."""
    item = type(item).objects.select_for_update().get(pk=item.pk)
    if item.hidden_at:
        raise APIError(409, "CONFLICT", "이미 숨긴 것이에요.")
    type(item).objects.filter(pk=item.pk).update(hidden_at=timezone.now(), hidden_reason=reason, hidden_by=admin)
    log(admin, HIDE_TARGETS[target_type][0], target_type, item.pk, reason)


@transaction.atomic
def unhide(item, target_type, admin, reason):
    """숨김을 되돌린다. 숨겨져 있지 않으면 409. 사유는 관리 기록에만 남는다."""
    item = type(item).objects.select_for_update().get(pk=item.pk)
    if not item.hidden_at:
        raise APIError(409, "CONFLICT", "숨겨져 있지 않아요.")
    type(item).objects.filter(pk=item.pk).update(hidden_at=None, hidden_reason=None, hidden_by=None)
    log(admin, HIDE_TARGETS[target_type][1], target_type, item.pk, reason)


def check_sanction_target(user, admin):
    if user.pk == admin.pk or user.is_service_admin:
        raise APIError(403, "FORBIDDEN", "관리자는 이용 제한할 수 없어요.")


@transaction.atomic
def sanction(user, admin, reason, ends_at):
    """이용 제한을 건다. ends_at 이 None 이면 영구. 이미 제한 중이면 409 (먼저 해제하고 다시 건다)."""
    check_sanction_target(user, admin)
    type(user).objects.select_for_update().get(pk=user.pk)  # 같은 회원을 동시에 두 번 제한하지 않게
    if current_sanction(user) is not None:
        raise APIError(409, "CONFLICT", "이미 이용 제한 중인 회원이에요.")
    created = UserSanction.objects.create(user=user, admin=admin, reason=reason, starts_at=timezone.now(), ends_at=ends_at)
    log(admin, "SANCTION_USER", "user", user.pk, reason)
    return created


@transaction.atomic
def release(user, admin, reason):
    """기한 전에 이용 제한을 푼다. 제한 중이 아니면 409."""
    type(user).objects.select_for_update().get(pk=user.pk)
    current = current_sanction(user)
    if current is None:
        raise APIError(409, "CONFLICT", "이용 제한 중이 아니에요.")
    current.released_at = timezone.now()
    current.released_by = admin
    current.save(update_fields=["released_at", "released_by"])
    log(admin, "RELEASE_USER", "user", user.pk, reason)
    return current
