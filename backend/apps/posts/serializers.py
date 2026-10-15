"""기록 · 방 · 태그 요청 검사와 응답 모양 (API 명세서 3.3, 4.3, 4.4)."""

import base64
import binascii
from datetime import datetime

from django.conf import settings
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from rest_framework import serializers

from apps.common.errors import APIError

from .content import media_url

MAX_TAGS = 10


# ----- 요청 -----
class PostWriteSerializer(serializers.Serializer):
    """발행(POST) · 수정(PATCH) 요청. 수정은 partial=True 로 바꿀 것만 받는다."""

    title = serializers.CharField(
        max_length=100,
        trim_whitespace=True,
        error_messages={"blank": "제목을 써 주세요.", "required": "제목을 써 주세요.", "max_length": "제목은 1~100자로 써 주세요."},
    )
    content = serializers.CharField(trim_whitespace=False, error_messages={"blank": "본문을 써 주세요.", "required": "본문을 써 주세요."})
    category_id = serializers.IntegerField(required=False, allow_null=True)
    topic_slug = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField(trim_whitespace=True, allow_blank=True), required=False)
    visibility = serializers.ChoiceField(
        choices=["PUBLIC", "PRIVATE", "SUBSCRIBERS"], required=False, error_messages={"invalid_choice": "공개 범위를 다시 골라 주세요."}
    )
    cover_image_id = serializers.IntegerField(required=False, allow_null=True)
    image_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    client_token = serializers.CharField(max_length=36, required=False, allow_null=True)

    def validate_visibility(self, value):
        if value == "SUBSCRIBERS":
            raise serializers.ValidationError("이웃 공개는 아직 준비 중이에요.")
        return value

    def validate_tags(self, value):
        tags = []
        for raw in value:
            name = raw.lstrip("#").strip()
            if not name:
                continue
            if len(name) > 20:
                raise serializers.ValidationError("태그는 20자까지 쓸 수 있어요.")
            # 영문 대소문자만 다르면 같은 태그 (TAG-01)
            if name.lower() not in (t.lower() for t in tags):
                tags.append(name)
        if len(tags) > MAX_TAGS:
            raise serializers.ValidationError("태그는 10개까지 붙일 수 있어요.")
        return tags


class CategoryCreateSerializer(serializers.Serializer):
    name = serializers.CharField(
        max_length=20,
        trim_whitespace=True,
        error_messages={"blank": "방 이름을 써 주세요.", "required": "방 이름을 써 주세요.", "max_length": "방 이름은 1~20자로 써 주세요."},
    )


# ----- 목록 나누기 (API 명세서 2.5) -----
def page_params(request):
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        size = min(50, max(1, int(request.query_params.get("size", 10))))
    except ValueError:
        raise APIError(400, "VALIDATION_ERROR", "입력한 내용을 확인해 주세요.", fields={"page": "숫자로 보내 주세요."})
    return page, size


def paginate(queryset, request, to_item):
    page, size = page_params(request)
    total = queryset.count()
    rows = queryset[(page - 1) * size: page * size]
    return {
        "items": [to_item(row) for row in rows],
        "page": page,
        "size": size,
        "total": total,
        "total_pages": (total + size - 1) // size,
    }


def encode_cursor(post):
    raw = f"{post.published_at.isoformat()}|{post.pk}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def cursor_page(queryset, request, to_item):
    """최신순 커서 목록. 커서는 (published_at, id) 라 더 불러오는 사이 새 글이 와도 겹치거나 빠지지 않는다."""
    try:
        limit = min(50, max(1, int(request.query_params.get("limit", 20))))
    except ValueError:
        limit = 20
    cursor = request.query_params.get("cursor")
    qs = queryset.order_by("-published_at", "-id")
    if cursor:
        try:
            when, pk = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
            when = datetime.fromisoformat(when)
            pk = int(pk)
        except (ValueError, binascii.Error, UnicodeDecodeError):
            raise APIError(400, "VALIDATION_ERROR", "입력한 내용을 확인해 주세요.", fields={"cursor": "잘못된 커서예요."})
        qs = qs.filter(Q(published_at__lt=when) | Q(published_at=when, id__lt=pk))
    rows = list(qs[: limit + 1])
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [to_item(row) for row in rows], "next_cursor": encode_cursor(rows[-1]) if more and rows else None}


# ----- 응답 -----
def with_counts(queryset):
    """공감 · 댓글 수를 붙인다. 조인이 겹쳐 수가 부풀지 않도록 서브쿼리로 센다."""
    from apps.community.models import Comment, PostLike

    likes = PostLike.objects.filter(post=OuterRef("pk")).values("post").annotate(n=Count("pk")).values("n")
    comments = (
        Comment.objects.filter(post=OuterRef("pk"), hidden_at__isnull=True).values("post").annotate(n=Count("pk")).values("n")
    )
    return queryset.select_related("blog", "category", "topic", "cover_image", "first_image").annotate(
        like_total=Coalesce(Subquery(likes, output_field=IntegerField()), 0),
        comment_total=Coalesce(Subquery(comments, output_field=IntegerField()), 0),
    )


def thumbnail_url(post, request):
    image = post.cover_image or post.first_image
    return media_url(image.thumb_file.name) if image else None


def hidden_notice(post):
    """관리자가 숨긴 기록이면 주인에게 숨김 사실과 사유를 알린다 (ADMIN-03). 아니면 None."""
    if not post.hidden_at:
        return None
    return {"at": post.hidden_at, "reason": post.hidden_reason}


def post_summary(post, request, owner_view=False):
    """PostSummary (API 명세서 3.3). post 는 with_counts() 를 거친 것이어야 한다.
    주인이 자기 목록을 볼 때는 view_count 와 hidden(관리자 숨김)이 더 붙는다."""
    data = {
        "blog": {"address": post.blog.address, "name": post.blog.name},
        "no": post.post_no,
        "title": post.title,
        "excerpt": post.excerpt,
        "thumbnail_url": thumbnail_url(post, request),
        "category": {"id": post.category_id, "name": post.category.name} if post.category else None,
        "topic": {"slug": post.topic.slug, "name": post.topic.name} if post.topic else None,
        "published_at": post.published_at,
        "like_count": post.like_total,
        "comment_count": post.comment_total,
        "visibility": post.visibility,
    }
    if owner_view:
        data["view_count"] = post.view_count
        data["hidden"] = hidden_notice(post)
    return data


def post_url(post):
    """화면 주소. 서비스 도메인이 정해지면 {주소}.한채도메인/{no} (API 명세서 4.3)."""
    if settings.HANCHAE_DOMAIN:
        return f"{settings.SCHEME}://{post.blog.address}.{settings.HANCHAE_DOMAIN}/{post.post_no}"
    return None


def published_order(queryset):
    return queryset.order_by("-published_at", "-id")


def tag_names(post):
    return [pt.tag.name for pt in post.post_tags.select_related("tag").order_by("tag__name")]

