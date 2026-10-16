"""마을 관리 API /api/admin/* (ADMIN-01 · 02 · 03, 명세 contracts/pages.md 관리 영역).

모두 서비스 관리자(role = ADMIN)만 부른다. 남의 글 · 댓글 내용을 고치는 기능은 두지 않는다 (ADMIN-01a).
"""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.pending import pending_signups
from apps.common.access import active_sanctions
from apps.common.permissions import IsServiceAdmin
from apps.community.models import Comment, GuestbookEntry
from apps.posts.models import Post
from apps.posts.serializers import paginate

from . import services

User = get_user_model()


# ----- 요청 -----
def reason_field(max_length):
    return serializers.CharField(
        max_length=max_length,
        trim_whitespace=True,
        error_messages={
            "blank": "사유를 써 주세요.",
            "required": "사유를 써 주세요.",
            "null": "사유를 써 주세요.",
            "max_length": f"사유는 {max_length:,}자까지 쓸 수 있어요.",
        },
    )


class HideSerializer(serializers.Serializer):
    reason = reason_field(200)  # posts · comments 의 hidden_reason 길이


class SanctionSerializer(serializers.Serializer):
    reason = reason_field(500)
    # 영구 제한은 null 로 분명히 보낸다. 빠뜨린 것과 구분하려고 필수로 둔다
    ends_at = serializers.DateTimeField(
        allow_null=True, error_messages={"required": "끝나는 날을 고르거나 영구를 골라 주세요."}
    )

    def validate_ends_at(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("끝나는 날은 지금보다 뒤여야 해요.")
        return value


class ReleaseSerializer(serializers.Serializer):
    reason = reason_field(500)


def validated(serializer_class, request):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def search_text(request):
    return request.query_params.get("q", "").strip()


# ----- 응답 -----
def person(user):
    return {"id": user.pk, "nickname": user.nickname, "email": user.email}


def hidden_info(item):
    if not item.hidden_at:
        return None
    return {"at": item.hidden_at, "reason": item.hidden_reason, "by": item.hidden_by.nickname if item.hidden_by else None}


def sanction_info(sanction):
    if sanction is None:
        return None
    return {
        "id": sanction.pk,
        "reason": sanction.reason,
        "starts_at": sanction.starts_at,
        "ends_at": sanction.ends_at,
        "admin": sanction.admin.nickname,
    }


def post_row(post):
    return {
        "id": post.pk,
        "blog": {"address": post.blog.address, "name": post.blog.name},
        "author": person(post.blog.owner),
        "no": post.post_no,
        "title": post.title,
        "excerpt": post.excerpt,
        "visibility": post.visibility,
        "published_at": post.published_at,
        "hidden": hidden_info(post),
    }


def comment_row(comment):
    post = comment.post
    return {
        "id": comment.pk,
        "author": person(comment.author),
        "content": comment.content,
        "created_at": comment.created_at,
        "hidden": hidden_info(comment),
        "post": {"id": post.pk, "title": post.title, "blog_address": post.blog.address, "no": post.post_no},
    }


def guestbook_row(entry):
    return {
        "id": entry.pk,
        "author": person(entry.author),
        "content": entry.content,
        "created_at": entry.created_at,
        "hidden": hidden_info(entry),
        "blog": {"address": entry.blog.address, "name": entry.blog.name},
    }


class AdminView(APIView):
    permission_classes = [IsServiceAdmin]


# ----- 회원 · 이용 제한 (ADMIN-02) -----
class UsersView(AdminView):
    """GET /api/admin/users?q= — 닉네임 · 이메일 · 한채 주소로 찾는다. 이메일 인증을 안 마친 가입은 회원이 아니라 뺀다."""

    def get(self, request):
        qs = (
            User.objects.filter(is_active=True)
            .exclude(pk__in=pending_signups().values("pk"))
            .order_by("-created_at", "-id")
        )
        q = search_text(request)
        if q:
            qs = qs.filter(Q(nickname__icontains=q) | Q(email__icontains=q) | Q(blogs__address__icontains=q)).distinct()
        sanctions = {}
        page = paginate(qs.prefetch_related("blogs"), request, lambda u: u)
        for s in active_sanctions().filter(user__in=page["items"]).select_related("admin").order_by("starts_at"):
            sanctions[s.user_id] = s

        def row(user):
            blog = next((b for b in user.blogs.all() if b.deleted_at is None), None)
            return {
                **person(user),
                "role": user.role,
                "created_at": user.created_at,
                "blog": {"address": blog.address, "name": blog.name} if blog else None,
                "sanction": sanction_info(sanctions.get(user.pk)),
            }

        page["items"] = [row(u) for u in page["items"]]
        return Response(page)


class UserSanctionView(AdminView):
    """POST /api/admin/users/{id}/sanctions — { reason, ends_at(null 이면 영구) }"""

    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id, is_active=True)
        data = validated(SanctionSerializer, request)
        created = services.sanction(user, request.user, data["reason"], data["ends_at"])
        return Response({"sanction": sanction_info(created)}, status=status.HTTP_201_CREATED)


class UserReleaseView(AdminView):
    """POST /api/admin/users/{id}/release — { reason }"""

    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        data = validated(ReleaseSerializer, request)
        services.release(user, request.user, data["reason"])
        return Response({"sanction": None})


# ----- 기록 숨김 (ADMIN-03) -----
def admin_posts():
    # 임시저장은 아직 아무에게도 보이지 않은 글이라 관리 대상이 아니다
    return Post.objects.filter(status=Post.Status.PUBLISHED).select_related("blog__owner", "hidden_by")


class PostsView(AdminView):
    """GET /api/admin/posts?q= — 제목 · 한채 주소 · 한채 이름 · 주인 닉네임으로 찾는다. 비공개 · 숨긴 기록도 나온다."""

    def get(self, request):
        qs = admin_posts().order_by("-published_at", "-id")
        q = search_text(request)
        if q:
            qs = qs.filter(
                Q(title__icontains=q) | Q(blog__address__icontains=q) | Q(blog__name__icontains=q)
                | Q(blog__owner__nickname__icontains=q)
            )
        return Response(paginate(qs, request, post_row))


class PostDetailView(AdminView):
    """GET /api/admin/posts/{id} — 제재에 필요한 범위에서 본문과 댓글을 본다 (권한표)."""

    def get(self, request, post_id):
        post = get_object_or_404(admin_posts(), pk=post_id)
        comments = post.comments.select_related("author", "hidden_by", "post__blog")
        return Response({**post_row(post), "content": post.content, "comments": [comment_row(c) for c in comments]})


class HideView(AdminView):
    """POST /api/admin/{posts|comments|guestbook}/{id}/hide · unhide — { reason }"""

    target_type = None
    unhide = False

    def queryset(self):
        if self.target_type == "post":
            return admin_posts()
        if self.target_type == "comment":
            return Comment.objects.all()
        return GuestbookEntry.objects.all()

    def post(self, request, item_id):
        item = get_object_or_404(self.queryset(), pk=item_id)
        data = validated(HideSerializer, request)
        action = services.unhide if self.unhide else services.hide
        action(item, self.target_type, request.user, data["reason"])
        item.refresh_from_db()
        return Response({"hidden": hidden_info(item)})


# ----- 댓글 · 방명록 찾기 -----
class CommentsView(AdminView):
    """GET /api/admin/comments?q= — 내용 · 쓴 사람 닉네임 · 한채 주소로 찾는다."""

    def get(self, request):
        qs = Comment.objects.select_related("author", "hidden_by", "post__blog").order_by("-created_at", "-id")
        q = search_text(request)
        if q:
            qs = qs.filter(Q(content__icontains=q) | Q(author__nickname__icontains=q) | Q(post__blog__address__icontains=q))
        return Response(paginate(qs, request, comment_row))


class GuestbookView(AdminView):
    """GET /api/admin/guestbook?q= — 내용 · 쓴 사람 닉네임 · 한채 주소로 찾는다."""

    def get(self, request):
        qs = GuestbookEntry.objects.select_related("author", "hidden_by", "blog").order_by("-created_at", "-id")
        q = search_text(request)
        if q:
            qs = qs.filter(Q(content__icontains=q) | Q(author__nickname__icontains=q) | Q(blog__address__icontains=q))
        return Response(paginate(qs, request, guestbook_row))
