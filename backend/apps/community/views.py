"""댓글 · 공감 · 이웃 API (API 명세서 4.5 · 4.6 · 4.7)."""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import user_summary
from apps.common.access import get_visible_blog_or_404, visible_blogs, visible_posts
from apps.common.errors import APIError
from apps.common.permissions import IsMember
from apps.blogs.serializers import blog_summary
from apps.posts.serializers import cursor_page, paginate, post_summary, with_counts
from apps.posts.views import visible_post_or_404

from .models import Comment, GuestbookEntry, PostLike, Subscription


class CommentWriteSerializer(serializers.Serializer):
    content = serializers.CharField(
        max_length=1000,
        trim_whitespace=True,
        error_messages={
            "blank": "댓글을 써 주세요.",
            "required": "댓글을 써 주세요.",
            "max_length": "댓글은 1,000자까지 쓸 수 있어요.",
        },
    )
    client_token = serializers.CharField(max_length=36, required=False, allow_null=True)


class GuestbookWriteSerializer(CommentWriteSerializer):
    content = serializers.CharField(
        max_length=1000,
        trim_whitespace=True,
        error_messages={
            "blank": "한마디를 써 주세요.",
            "required": "한마디를 써 주세요.",
            "max_length": "방명록은 1,000자까지 쓸 수 있어요.",
        },
    )


def comment_payload(comment, request, blog_owner_id):
    """Comment (API 명세서 3.4). 수정 · 삭제 가능 여부는 보는 사람 기준."""
    viewer = request.user
    is_author = viewer.is_authenticated and comment.author_id == viewer.pk
    is_blog_owner = viewer.is_authenticated and blog_owner_id == viewer.pk
    data = {
        "id": comment.pk,
        "author": user_summary(comment.author, request),
        "content": comment.content,
        "created_at": comment.created_at,
        "edited_at": comment.edited_at,
        "can_edit": is_author,
        "can_delete": is_author or is_blog_owner,
    }
    if comment.hidden_at:
        data.update({"content": None, "hidden": True, "can_edit": False})
    return data


def guestbook_payload(entry, request, blog_owner_id):
    """방명록 한 줄: Comment 모양에 남긴 사람의 한채(현판 이름)를 더한다."""
    data = comment_payload(entry, request, blog_owner_id)
    house = None
    if entry.author.is_active:
        blog = visible_blogs(entry.author.blogs.all()).only("address", "name").first()
        if blog:
            house = {"address": blog.address, "name": blog.name}
    data["author_blog"] = house
    return data


class PostCommentsView(APIView):
    """GET · POST /api/blogs/{address}/posts/{no}/comments — 댓글 보기 · 쓰기 (CMT-01)."""

    throttle_scope = "comment"  # 쓰기(POST)만 센다

    def get(self, request, address, no):
        blog = get_visible_blog_or_404(address, request.user)
        post = visible_post_or_404(blog, no, request.user)
        comments = post.comments.select_related("author")
        items = [comment_payload(c, request, blog.owner_id) for c in comments]
        return Response({"items": items, "count": sum(1 for c in comments if not c.hidden_at)})

    def post(self, request, address, no):
        if not request.user.is_authenticated:
            raise APIError(401, "AUTH_REQUIRED", "로그인하면 댓글을 남길 수 있어요.")
        blog = get_visible_blog_or_404(address, request.user)
        post = visible_post_or_404(blog, no, request.user)
        serializer = CommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        token = data.get("client_token") or None

        # 같은 client_token 이 다시 오면 처음 만든 댓글을 돌려준다 (API 명세서 2.6)
        if token:
            existing = Comment.objects.filter(author=request.user, client_token=token).first()
            if existing:
                return Response(comment_payload(existing, request, blog.owner_id))
        try:
            with transaction.atomic():
                comment = Comment.objects.create(post=post, author=request.user, content=data["content"], client_token=token)
        except IntegrityError:
            existing = Comment.objects.filter(author=request.user, client_token=token).first()
            if existing is None:
                raise
            return Response(comment_payload(existing, request, blog.owner_id))
        return Response(comment_payload(comment, request, blog.owner_id), status=status.HTTP_201_CREATED)


class CommentDetailView(APIView):
    """PATCH · DELETE /api/comments/{id} — 고치기는 작성자만, 지우기는 작성자 · 한채 주인 (CMT-01 · 02 · 03)."""

    permission_classes = [IsMember]

    def find(self, request, comment_id):
        comment = Comment.objects.select_related("post__blog", "author").filter(pk=comment_id).first()
        # 볼 수 없는 기록의 댓글은 없는 것처럼
        if comment is None or not visible_posts(request.user).filter(pk=comment.post_id).exists():
            raise APIError(404, "NOT_FOUND", "찾는 댓글이 없어요.")
        return comment

    def patch(self, request, comment_id):
        comment = self.find(request, comment_id)
        if comment.author_id != request.user.pk or comment.hidden_at:
            raise APIError(403, "FORBIDDEN", "내가 쓴 댓글만 고칠 수 있어요.")
        serializer = CommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment.content = serializer.validated_data["content"]
        comment.edited_at = timezone.now()
        comment.save(update_fields=["content", "edited_at", "updated_at"])
        return Response(comment_payload(comment, request, comment.post.blog.owner_id))

    def delete(self, request, comment_id):
        comment = self.find(request, comment_id)
        if request.user.pk not in (comment.author_id, comment.post.blog.owner_id):
            raise APIError(403, "FORBIDDEN", "내 댓글이나 내 한채의 댓글만 지울 수 있어요.")
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PostLikeView(APIView):
    """PUT · DELETE /api/blogs/{address}/posts/{no}/like — 공감 · 취소. 몇 번 보내도 결과가 같다 (SOC-01)."""

    permission_classes = [IsMember]

    def target(self, request, address, no):
        blog = get_visible_blog_or_404(address, request.user)
        post = visible_post_or_404(blog, no, request.user)
        if blog.owner_id == request.user.pk:
            raise APIError(422, "NOT_ALLOWED", "내 기록에는 공감할 수 없어요.")
        return post

    def result(self, post, liked):
        return Response({"liked": liked, "like_count": PostLike.objects.filter(post=post).count()})

    def put(self, request, address, no):
        post = self.target(request, address, no)
        try:
            with transaction.atomic():
                PostLike.objects.get_or_create(post=post, user=request.user)
        except IntegrityError:
            pass  # 동시에 두 번 눌렀다
        return self.result(post, True)

    def delete(self, request, address, no):
        post = self.target(request, address, no)
        PostLike.objects.filter(post=post, user=request.user).delete()
        return self.result(post, False)


class SubscriptionView(APIView):
    """PUT · DELETE /api/blogs/{address}/subscription — 이웃 맺기 · 끊기 (SUB-01)."""

    permission_classes = [IsMember]

    def target(self, request, address):
        blog = get_visible_blog_or_404(address, request.user)
        if blog.owner_id == request.user.pk:
            raise APIError(422, "NOT_ALLOWED", "내 한채와는 이웃을 맺을 수 없어요.")
        return blog

    def result(self, blog, subscribed):
        return Response({"subscribed": subscribed, "subscriber_count": Subscription.objects.filter(blog=blog).count()})

    def put(self, request, address):
        blog = self.target(request, address)
        try:
            with transaction.atomic():
                Subscription.objects.get_or_create(blog=blog, subscriber=request.user)
        except IntegrityError:
            pass
        return self.result(blog, True)

    def delete(self, request, address):
        blog = self.target(request, address)
        Subscription.objects.filter(blog=blog, subscriber=request.user).delete()
        return self.result(blog, False)


class FeedView(APIView):
    """GET /api/me/feed — 이웃 한채의 새 기록, 최신순 커서 (SUB-02)."""

    permission_classes = [IsMember]

    def get(self, request):
        blogs = visible_blogs().filter(subscriptions__subscriber=request.user)
        qs = with_counts(visible_posts(request.user).filter(blog__in=blogs))
        return Response(cursor_page(qs, request, lambda p: post_summary(p, request)))


class GuestbookView(APIView):
    """GET · POST /api/blogs/{address}/guestbook — 방명록 보기(최신순, 페이지) · 남기기 (CMT-04)."""

    throttle_scope = "guestbook"  # 남기기(POST)만 센다

    def get(self, request, address):
        blog = get_visible_blog_or_404(address, request.user)
        entries = GuestbookEntry.objects.filter(blog=blog).select_related("author").order_by("-created_at", "-id")
        return Response(paginate(entries, request, lambda e: guestbook_payload(e, request, blog.owner_id)))

    def post(self, request, address):
        if not request.user.is_authenticated:
            raise APIError(401, "AUTH_REQUIRED", "로그인하면 방명록을 남길 수 있어요.")
        blog = get_visible_blog_or_404(address, request.user)
        serializer = GuestbookWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        token = data.get("client_token") or None
        if token:
            existing = GuestbookEntry.objects.filter(author=request.user, client_token=token).first()
            if existing:
                return Response(guestbook_payload(existing, request, blog.owner_id))
        try:
            with transaction.atomic():
                entry = GuestbookEntry.objects.create(blog=blog, author=request.user, content=data["content"], client_token=token)
        except IntegrityError:
            existing = GuestbookEntry.objects.filter(author=request.user, client_token=token).first()
            if existing is None:
                raise
            return Response(guestbook_payload(existing, request, blog.owner_id))
        return Response(guestbook_payload(entry, request, blog.owner_id), status=status.HTTP_201_CREATED)


class GuestbookDetailView(APIView):
    """PATCH · DELETE /api/guestbook/{id} — 고치기는 쓴 사람만, 지우기는 쓴 사람 · 한채 주인 (CMT-04)."""

    permission_classes = [IsMember]

    def find(self, request, entry_id):
        entry = GuestbookEntry.objects.select_related("blog", "author").filter(pk=entry_id).first()
        if entry is None:
            raise APIError(404, "NOT_FOUND", "찾는 방명록이 없어요.")
        get_visible_blog_or_404(entry.blog.address, request.user)  # 볼 수 없는 한채면 404
        return entry

    def patch(self, request, entry_id):
        entry = self.find(request, entry_id)
        if entry.author_id != request.user.pk or entry.hidden_at:
            raise APIError(403, "FORBIDDEN", "내가 남긴 방명록만 고칠 수 있어요.")
        serializer = GuestbookWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry.content = serializer.validated_data["content"]
        entry.edited_at = timezone.now()
        entry.save(update_fields=["content", "edited_at", "updated_at"])
        return Response(guestbook_payload(entry, request, entry.blog.owner_id))

    def delete(self, request, entry_id):
        entry = self.find(request, entry_id)
        if request.user.pk not in (entry.author_id, entry.blog.owner_id):
            raise APIError(403, "FORBIDDEN", "내 방명록이나 내 한채의 방명록만 지울 수 있어요.")
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MySubscriptionsView(APIView):
    """GET /api/me/subscriptions — 내 이웃 한채, 이웃 맺은 최신순 페이지 (SUB-01)."""

    permission_classes = [IsMember]

    def get(self, request):
        subs = (
            Subscription.objects.filter(subscriber=request.user, blog__in=visible_blogs())
            .select_related("blog__owner")
            .order_by("-created_at", "-id")
        )

        def item(sub):
            data = blog_summary(sub.blog, request)
            data["post_count"] = visible_posts(request.user).filter(blog=sub.blog).count()
            return data

        return Response(paginate(subs, request, item))
