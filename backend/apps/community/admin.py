from django.contrib import admin

from .models import PostLike, Subscription

# 댓글 · 방명록은 등록하지 않는다. 숨김은 마을 관리(/admin)에서만 한다 (contracts/pages.md, ADMIN-01a)
admin.site.register(PostLike)
admin.site.register(Subscription)
