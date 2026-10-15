from django.contrib import admin

from .models import AdminLog, UserSanction


class ReadOnlyAdmin(admin.ModelAdmin):
    """운영 화면에서는 보기만 한다. 제한 · 해제는 사유와 기록이 남는 마을 관리(/admin)에서 한다."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserSanction)
class UserSanctionAdmin(ReadOnlyAdmin):
    list_display = ["id", "user", "reason", "starts_at", "ends_at", "released_at", "admin"]


@admin.register(AdminLog)
class AdminLogAdmin(ReadOnlyAdmin):
    list_display = ["id", "created_at", "admin", "action", "target_type", "target_id", "reason"]
    list_filter = ["action", "target_type"]
