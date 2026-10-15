"""기록 · 방 · 태그 · 마을 목록 API (API 명세서 4.3, 4.4, 4.9)."""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, Exists, F, IntegerField, OuterRef, Q, Value, When
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.access import get_visible_blog_or_404, visible_blogs, visible_posts
from apps.common.errors import APIError
from apps.common.permissions import IsMember

from . import writing
from .images import image_payload, save_upload
from .models import Category, Post, PostTag, PostView, Tag, Topic
from .serializers import (
    CategoryCreateSerializer,
    PostWriteSerializer,
    cursor_page,
    hidden_notice,
    paginate,
    post_summary,
    post_url,
    published_order,
    tag_names,
    with_counts,
)

VIEW_DEDUP_WINDOW = timedelta(minutes=30)
VISITOR_COOKIE = "hc_vid"


def owned_blog(address, user):
    """주인만 하는 일: 로그인 안 함 401, 주인 아님 403 (API 명세서 2.3)."""
    if not user.is_authenticated:
        raise APIError(401, "AUTH_REQUIRED", "로그인이 필요해요.")
    blog = get_visible_blog_or_404(address, user)
    if blog.owner_id != user.pk:
        raise APIError(403, "FORBIDDEN", "이 한채의 주인만 할 수 있어요.")
    return blog


def visible_post_or_404(blog, no, viewer):
    post = with_counts(visible_posts(viewer).filter(blog=blog, post_no=no)).first()
    if post is None:
        raise APIError(404, "NOT_FOUND", "찾는 기록이 없어요.")
    return post


def public_feed(viewer):
    """마을 목록: 볼 수 있는 한채의 공개 기록."""
    return visible_posts(viewer).filter(visibility=Post.Visibility.PUBLIC, blog__in=visible_blogs())


class ImageUploadView(APIView):
    """POST /api/images — 이미지 올리기 (multipart/form-data, 필드 file)."""

    permission_classes = [IsMember]

    def post(self, request):
        image = save_upload(request.FILES.get("file"), request.user)
        return Response(image_payload(image, request), status=status.HTTP_201_CREATED)


class TopicListView(APIView):
    """GET /api/topics — 골목 10개."""

    def get(self, request):
        return Response([{"slug": t.slug, "name": t.name} for t in Topic.objects.all()])


class BlogPostsView(APIView):
    """GET · POST /api/blogs/{address}/posts — 한채 안 기록 목록 · 기록 발행 (POST-01, BLOG-03 …)."""

    def get(self, request, address):
        blog = get_visible_blog_or_404(address, request.user)
        is_owner = request.user.is_authenticated and blog.owner_id == request.user.pk
        qs = visible_posts(request.user).filter(blog=blog)
        params = request.query_params

        # 거르는 값은 하나만 쓴다 (API 명세서 4.3)
        if "category" in params:
            category = params["category"]
            if category == "none":
                qs = qs.filter(category__isnull=True)  # 마루
            elif category.isdigit():
                qs = qs.filter(category_id=int(category))
            else:
                qs = qs.none()
        elif params.get("tag"):
            qs = qs.filter(post_tags__tag__name__iexact=params["tag"])
        elif "q" in params:
            q = params["q"].strip()
            if not q:
                raise APIError(400, "VALIDATION_ERROR", "입력한 내용을 확인해 주세요.", fields={"q": "찾을 말을 써 주세요."})
            qs = qs.filter(
                Q(title__icontains=q) | Q(content_text__icontains=q) | Q(post_tags__tag__name__icontains=q)
            ).distinct()
        elif params.get("visibility") and is_owner:
            qs = qs.filter(visibility=params["visibility"])

        return Response(paginate(published_order(with_counts(qs)), request, lambda p: post_summary(p, request, is_owner)))

    def post(self, request, address):
        blog = owned_blog(address, request.user)
        serializer = PostWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 같은 client_token 이 다시 오면 처음 만든 기록을 돌려준다 (API 명세서 2.6)
        token = data.get("client_token")
        if token:
            existing = Post.objects.filter(blog=blog, client_token=token).first()
            if existing:
                return Response({"no": existing.post_no, "url": post_url(existing)})
        try:
            with transaction.atomic():
                post = writing.publish(blog, data)
        except IntegrityError:
            existing = Post.objects.filter(blog=blog, client_token=token).first() if token else None
            if existing is None:
                raise
            return Response({"no": existing.post_no, "url": post_url(existing)})
        return Response({"no": post.post_no, "url": post_url(post)}, status=status.HTTP_201_CREATED)


class PostDetailView(APIView):
    """GET · PATCH · DELETE /api/blogs/{address}/posts/{no} (POST-02 · 03 · 04 · 10)."""

    def get(self, request, address, no):
        blog = get_visible_blog_or_404(address, request.user)
        post = visible_post_or_404(blog, no, request.user)
        viewer = request.user
        siblings = visible_posts(viewer).filter(blog=blog)
        older = siblings.filter(
            Q(published_at__lt=post.published_at) | Q(published_at=post.published_at, id__lt=post.pk)
        ).order_by("-published_at", "-id").first()
        newer = siblings.filter(
            Q(published_at__gt=post.published_at) | Q(published_at=post.published_at, id__gt=post.pk)
        ).order_by("published_at", "id").first()

        is_owner = viewer.is_authenticated and blog.owner_id == viewer.pk
        data = post_summary(post, request)
        data.update(
            {
                "content": post.content,
                "tags": tag_names(post),
                "view_count": post.view_count,
                "liked_by_me": viewer.is_authenticated and post.likes.filter(user=viewer).exists(),
                "is_owner": is_owner,
                "prev": {"no": older.post_no, "title": older.title} if older else None,
                "next": {"no": newer.post_no, "title": newer.title} if newer else None,
            }
        )
        if is_owner:
            # 고치기 화면이 대표 이미지를 고를 때 쓴다 (명세서 밖, 주인에게만)
            data["cover_image_id"] = post.cover_image_id
            data["hidden"] = hidden_notice(post)
            images = [pi.image for pi in post.post_images.select_related("image")]
            if post.cover_image and post.cover_image not in images:
                images.append(post.cover_image)  # 본문과 따로 올린 대표 이미지
            data["images"] = [image_payload(img, request) for img in images]
        return Response(data)

    def patch(self, request, address, no):
        blog = owned_blog(address, request.user)
        post = Post.objects.filter(blog=blog, post_no=no, status=Post.Status.PUBLISHED).first()
        if post is None:
            raise APIError(404, "NOT_FOUND", "찾는 기록이 없어요.")
        serializer = PostWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = {k: v for k, v in serializer.validated_data.items() if k != "client_token"}
        with transaction.atomic():
            writing.update(post, data)
        return Response({"no": post.post_no, "url": post_url(post)})

    def delete(self, request, address, no):
        blog = owned_blog(address, request.user)
        deleted, _ = Post.objects.filter(blog=blog, post_no=no).delete()
        if not deleted:
            raise APIError(404, "NOT_FOUND", "찾는 기록이 없어요.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class PostViewCountView(APIView):
    """POST /api/blogs/{address}/posts/{no}/views — 조회 한 번 기록 (POST-09, ERD REQ-008).

    같은 방문자(회원 또는 hc_vid 쿠키)가 30분 안에 다시 부르면 세지 않고, 주인 본인의 조회도 세지 않는다.
    """

    def post(self, request, address, no):
        blog = get_visible_blog_or_404(address, request.user)
        post = visible_post_or_404(blog, no, request.user)
        response = Response(status=status.HTTP_204_NO_CONTENT)

        visitor = request.COOKIES.get(VISITOR_COOKIE)
        if not visitor:
            visitor = secrets.token_urlsafe(16)
            response.set_cookie(
                VISITOR_COOKIE, visitor, max_age=60 * 60 * 24 * 365, httponly=True, samesite="Lax",
                secure=settings.USE_HTTPS, domain=settings.SESSION_COOKIE_DOMAIN,
            )
        if request.user.is_authenticated and blog.owner_id == request.user.pk:
            return response

        who = f"u:{request.user.pk}" if request.user.is_authenticated else f"v:{visitor}"
        viewer_key = hashlib.sha256(f"{settings.SECRET_KEY}:{who}".encode()).hexdigest()
        now = timezone.now()
        if not PostView.objects.filter(post=post, viewer_key=viewer_key, viewed_at__gte=now - VIEW_DEDUP_WINDOW).exists():
            PostView.objects.create(post=post, viewer_key=viewer_key, viewed_at=now)
            Post.objects.filter(pk=post.pk).update(view_count=F("view_count") + 1)
        return response


class CategoriesView(APIView):
    """GET · POST /api/blogs/{address}/categories — 방 안내 · 방 만들기 (CAT-01, CAT-02)."""

    def get(self, request, address):
        blog = get_visible_blog_or_404(address, request.user)
        posts = visible_posts(request.user).filter(blog=blog)
        counts = dict(posts.filter(category__isnull=False).values_list("category").annotate(n=Count("id")))
        rooms = [
            {"id": c.pk, "name": c.name, "post_count": counts.get(c.pk, 0)}
            for c in Category.objects.filter(blog=blog, parent__isnull=True)
        ]
        return Response(
            {
                "total_count": posts.count(),
                "rooms": rooms,
                "uncategorized_count": posts.filter(category__isnull=True).count(),
            }
        )

    def post(self, request, address):
        blog = owned_blog(address, request.user)
        serializer = CategoryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data["name"]
        last = Category.objects.filter(blog=blog).order_by("-sort_order").first()
        try:
            with transaction.atomic():
                category = Category.objects.create(blog=blog, name=name, sort_order=(last.sort_order + 1) if last else 0)
        except IntegrityError:
            raise APIError(409, "CONFLICT", "이미 있는 방 이름이에요.", fields={"name": "이미 있는 방 이름이에요."})
        return Response({"id": category.pk, "name": category.name, "post_count": 0}, status=status.HTTP_201_CREATED)


class CategoryDetailView(APIView):
    """PATCH · DELETE /api/blogs/{address}/categories/{id} — 방 이름 바꾸기 · 없애기 (CAT-01).
    없앤 방의 기록은 지우지 않고 마루(category NULL)로 옮긴다."""

    def target(self, request, address, category_id):
        blog = owned_blog(address, request.user)
        category = Category.objects.filter(blog=blog, pk=category_id).first()
        if category is None:
            raise APIError(404, "NOT_FOUND", "찾는 방이 없어요.")
        return category

    def patch(self, request, address, category_id):
        category = self.target(request, address, category_id)
        serializer = CategoryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category.name = serializer.validated_data["name"]
        try:
            with transaction.atomic():
                category.save(update_fields=["name", "updated_at"])
        except IntegrityError:
            raise APIError(409, "CONFLICT", "이미 있는 방 이름이에요.", fields={"name": "이미 있는 방 이름이에요."})
        return Response({"id": category.pk, "name": category.name})

    def delete(self, request, address, category_id):
        category = self.target(request, address, category_id)
        with transaction.atomic():
            moved = Post.objects.filter(category=category).update(category=None)
            category.delete()
        return Response({"moved_to_uncategorized": moved})


class CategoryOrderView(APIView):
    """PUT /api/blogs/{address}/categories/order — 방 순서 바꾸기 (CAT-04). 그 한채의 방 id 를 빠짐없이."""

    def put(self, request, address):
        blog = owned_blog(address, request.user)
        ids = request.data.get("ids") if isinstance(request.data, dict) else None
        current = list(Category.objects.filter(blog=blog, parent__isnull=True).values_list("pk", flat=True))
        if (
            not isinstance(ids, list)
            or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids)
            or len(ids) != len(set(ids))
            or set(ids) != set(current)
        ):
            raise APIError(400, "VALIDATION_ERROR", "방 순서를 다시 보내 주세요.", fields={"ids": "이 한채의 방을 빠짐없이 한 번씩 보내 주세요."})
        with transaction.atomic():
            for position, pk in enumerate(ids):
                Category.objects.filter(pk=pk).update(sort_order=position)
        return Response({"ids": ids})


class TagsView(APIView):
    """GET /api/blogs/{address}/tags — 이 한채의 태그, 많이 쓴 순 (TAG-03)."""

    def get(self, request, address):
        blog = get_visible_blog_or_404(address, request.user)
        posts = visible_posts(request.user).filter(blog=blog)
        tags = (
            Tag.objects.filter(blog=blog, post_tags__post__in=posts)
            .annotate(post_count=Count("post_tags__post", distinct=True))
            .order_by("-post_count", "name")
        )
        return Response([{"name": t.name, "post_count": t.post_count} for t in tags])


class NewPostsView(APIView):
    """GET /api/home/new-posts — 마을의 새 기록, 최신순 커서 (HOME-01)."""

    def get(self, request):
        return Response(cursor_page(with_counts(public_feed(request.user)), request, lambda p: post_summary(p, request)))


class TopicPostsView(APIView):
    """GET /api/topics/{slug}/posts — 골목의 기록, 최신순 커서 (HOME-03)."""

    def get(self, request, slug):
        topic = Topic.objects.filter(slug=slug).first()
        if topic is None:
            raise APIError(404, "NOT_FOUND", "없는 골목이에요.")
        qs = with_counts(public_feed(request.user).filter(topic=topic))
        return Response(cursor_page(qs, request, lambda p: post_summary(p, request)))


# ----- 마을에서 찾기 (API 명세서 4.8) -----
def search_query(request):
    q = (request.query_params.get("q") or "").strip()
    if not q:
        raise APIError(400, "VALIDATION_ERROR", "찾을 낱말을 써 주세요.", fields={"q": "찾을 낱말을 써 주세요."})
    if len(q) > 50:
        raise APIError(400, "VALIDATION_ERROR", "찾을 낱말은 50자까지 쓸 수 있어요.", fields={"q": "50자까지 쓸 수 있어요."})
    return q


class SearchPostsView(APIView):
    """GET /api/search/posts?q=&sort=relevance|latest&page= — 마을 전체의 공개 기록 찾기 (SRCH-02).

    정확도는 제목(3) · 태그(2) · 본문(1)에 낱말이 있는지 더한 점수, 같으면 최신순.
    """

    def get(self, request):
        q = search_query(request)
        sort = request.query_params.get("sort") or "relevance"
        if sort not in ("relevance", "latest"):
            raise APIError(400, "VALIDATION_ERROR", "정렬을 다시 골라 주세요.", fields={"sort": "relevance 또는 latest"})
        tag_hit = Exists(PostTag.objects.filter(post=OuterRef("pk"), tag__name__icontains=q))
        qs = (
            public_feed(request.user)
            .annotate(tag_hit=tag_hit)
            .filter(Q(title__icontains=q) | Q(content_text__icontains=q) | Q(tag_hit=True))
        )
        if sort == "latest":
            qs = qs.order_by("-published_at", "-id")
        else:
            score = (
                Case(When(title__icontains=q, then=Value(3)), default=Value(0), output_field=IntegerField())
                + Case(When(tag_hit=True, then=Value(2)), default=Value(0), output_field=IntegerField())
                + Case(When(content_text__icontains=q, then=Value(1)), default=Value(0), output_field=IntegerField())
            )
            qs = qs.annotate(score=score).order_by("-score", "-published_at", "-id")
        return Response(paginate(with_counts(qs), request, lambda p: post_summary(p, request)))


class SearchBlogsView(APIView):
    """GET /api/search/blogs?q=&page= — 한채 찾기 (이름 · 소개). 이름에 있으면 먼저, 같으면 이웃 많은 순 (SRCH-02)."""

    def get(self, request):
        from apps.blogs.serializers import blog_summary

        q = search_query(request)
        qs = (
            visible_blogs()
            .filter(Q(name__icontains=q) | Q(description__icontains=q))
            .select_related("owner")
            .annotate(
                name_hit=Case(When(name__icontains=q, then=Value(1)), default=Value(0), output_field=IntegerField()),
                subs=Count("subscriptions", distinct=True),
            )
            .order_by("-name_hit", "-subs", "-id")
        )
        return Response(paginate(qs, request, lambda b: blog_summary(b, request)))
