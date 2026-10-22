"""한채 API (API 명세서 4.2, 기능 BLOG-01 · BLOG-02 · SUB-03)."""

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.access import get_visible_blog_or_404, visible_posts
from apps.common.errors import APIError
from apps.common.permissions import IsMember
from apps.community.models import Subscription
from apps.posts.images import get_own_image

from apps.common.storage import delete_files
from apps.posts.views import owned_blog

from .demolish import demolish_blogs, demolish_summary
from .models import Blog
from .serializers import BlogCreateSerializer, BlogUpdateSerializer, blog_summary, check_address


def blog_detail(blog, request):
    viewer = request.user
    data = blog_summary(blog, request)
    data["post_count"] = visible_posts(viewer).filter(blog=blog).count()
    data["is_owner"] = viewer.is_authenticated and blog.owner_id == viewer.pk
    data["is_subscribed"] = (
        viewer.is_authenticated and Subscription.objects.filter(blog=blog, subscriber=viewer).exists()
    )
    return data


class AddressAvailableView(APIView):
    """GET /api/blogs/address-available?address= — 한채 주소를 쓸 수 있는지."""

    permission_classes = [IsMember]

    def get(self, request):
        problem = check_address(request.query_params.get("address", "").strip())
        return Response({"available": problem is None, "reason": problem})


class BlogCreateView(APIView):
    """POST /api/blogs — 한채 짓기. 회원당 살아 있는 한채는 하나 (BLOG-01)."""

    permission_classes = [IsMember]

    def post(self, request):
        if Blog.objects.filter(owner=request.user, deleted_at__isnull=True).exists():
            raise APIError(409, "CONFLICT", "이미 지은 한채가 있어요. 한 사람은 한 채만 지을 수 있어요.")
        serializer = BlogCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                blog = Blog.objects.create(owner=request.user, **serializer.validated_data)
        except IntegrityError:
            # 동시에 두 번 눌렀거나, 그 사이 같은 주소를 누가 먼저 가져갔다
            if Blog.objects.filter(owner=request.user, deleted_at__isnull=True).exists():
                raise APIError(409, "CONFLICT", "이미 지은 한채가 있어요. 한 사람은 한 채만 지을 수 있어요.")
            raise APIError(409, "CONFLICT", "이미 있거나 예약된 주소예요.", fields={"address": "이미 있거나 예약된 주소예요."})
        return Response(blog_detail(blog, request), status=status.HTTP_201_CREATED)


class BlogDetailView(APIView):
    """GET · PATCH /api/blogs/{address} — 대문 정보 보기 · 한채 관리 (BLOG-02)."""

    def get(self, request, address):
        blog = get_visible_blog_or_404(address, request.user)
        return Response(blog_detail(blog, request))

    def patch(self, request, address):
        if not request.user.is_authenticated:
            raise APIError(401, "AUTH_REQUIRED", "로그인이 필요해요.")
        blog = get_visible_blog_or_404(address, request.user)
        if blog.owner_id != request.user.pk:
            raise APIError(403, "FORBIDDEN", "이 한채의 주인만 바꿀 수 있어요.")
        serializer = BlogUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        for field in ("name", "description"):
            if field in data:
                setattr(blog, field, data[field])
        if "profile_image_id" in data:
            image_id = data["profile_image_id"]
            blog.profile_image = get_own_image(image_id, request.user).file.name if image_id is not None else None
        blog.save()
        return Response(blog_detail(blog, request))


class DemolishView(APIView):
    """GET · POST /api/blogs/{address}/demolish — 한채 허물기 (BLOG-04). 주인만, 계정은 그대로.

    GET: 확인 창에 보일 수 (기록 · 임시저장 · 방 · 받은 방명록 · 이웃)
    POST {address, agree}: 한채 주소를 그대로 적고 확인 체크를 해야 허문다. 무엇을 지우는지는 demolish.py
    """

    permission_classes = [IsMember]
    throttle_scope = "login"

    def get(self, request, address):
        return Response(demolish_summary(owned_blog(address, request.user)))

    def post(self, request, address):
        blog = owned_blog(address, request.user)
        if (request.data.get("address") or "").strip() != blog.address:
            raise APIError(400, "VALIDATION_ERROR", "한채 주소가 맞지 않아요.", fields={"address": "한채 주소가 맞지 않아요."})
        if request.data.get("agree") is not True:
            raise APIError(400, "VALIDATION_ERROR", "위 내용을 확인했다고 체크해 주세요.", fields={"agree": "위 내용을 확인했다고 체크해 주세요."})
        with transaction.atomic():
            files = demolish_blogs(Blog.objects.select_for_update().filter(pk=blog.pk), request.user)
            transaction.on_commit(lambda: delete_files(files))
        return Response({"demolished": True})

