from django.contrib import admin

from .models import Category, Image, Tag, Topic

# 기록(Post)은 등록하지 않는다. 남의 글을 고치는 길을 두지 않고, 숨김은 사유 · 기록이 남는
# 마을 관리(/admin)에서만 한다 (contracts/pages.md, ADMIN-01a)


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ["sort_order", "name", "slug"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["id", "blog", "name", "parent", "sort_order"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["id", "blog", "name"]


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ["id", "file", "uploader", "size_bytes", "created_at"]
