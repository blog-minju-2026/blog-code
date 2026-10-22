from django.contrib import admin
from django.http import HttpResponse
from rest_framework.throttling import BaseThrottle

from apps.common.errors import APIError

from . import attempts
from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["id", "email", "nickname", "role", "is_active", "created_at"]
    list_filter = ["role", "is_active"]
    search_fields = ["email", "nickname"]
    exclude = ["password", "groups", "user_permissions"]


# ----- 운영 화면(/django-admin/) 로그인: 비밀번호를 거듭 틀리면 잠시 막는다 -----
# 운영 화면은 DRF 의 요청 횟수 제한을 거치지 않으므로, 서비스 로그인과 같은 규칙(attempts)으로 계정마다 · IP 마다 센다
_admin_login = admin.site.login


def guarded_admin_login(request, extra_context=None):
    if request.method != "POST":
        return _admin_login(request, extra_context)
    keys = [
        "admin:" + request.POST.get("username", "").strip().lower(),
        "admin-ip:" + BaseThrottle().get_ident(request),
    ]
    try:
        for key in keys:
            attempts.ensure_not_locked(key)
    except APIError as e:
        return HttpResponse(e.message, status=429, content_type="text/plain; charset=utf-8")
    response = _admin_login(request, extra_context)
    # 맞으면 로그인 뒤 화면으로 넘어가고(302), 틀리면 같은 화면을 다시 보인다(200)
    for key in keys:
        if response.status_code == 302:
            attempts.clear(key)
        else:
            attempts.record_failure(key)
    return response


admin.site.login = guarded_admin_login
