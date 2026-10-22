"""한채 허물기 (BLOG-04): 주인만, 주소를 적고 확인해야, 계정은 그대로 두고 한채 안의 것만 지운다."""

import os
import shutil
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.tests import make_member
from apps.community.models import Comment, GuestbookEntry, PostLike, Subscription
from apps.posts.models import Category, Image, Post
from apps.posts.tests import png_bytes

from .models import Blog

TEMP_MEDIA = tempfile.mkdtemp(prefix="hanchae-test-demolish-")


def tearDownModule():
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


def publish(blog, no, **extra):
    return Post.objects.create(blog=blog, post_no=no, content="x", content_text="x", status="PUBLISHED", published_at=timezone.now(), **extra)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DemolishTests(APITestCase):
    def setUp(self):
        self.minju = make_member()
        self.seohyun = make_member(email="seohyun@example.com", nickname="서현")
        self.blog = Blog.objects.create(owner=self.minju, address="minju", name="민주의 한채")
        self.other = Blog.objects.create(owner=self.seohyun, address="seohyun", name="서현의 한채")
        self.post = publish(self.blog, 1)
        Blog.objects.filter(pk=self.blog.pk).update(last_post_no=1)  # 직접 만든 1번 다음부터 API 가 번호를 매기게
        Post.objects.create(blog=self.blog, content="", content_text="")  # 임시저장
        top = Category.objects.create(blog=self.blog, name="여행")
        Category.objects.create(blog=self.blog, name="제주", parent=top)
        GuestbookEntry.objects.create(blog=self.blog, author=self.seohyun, content="받은 방명록")
        Subscription.objects.create(blog=self.blog, subscriber=self.seohyun)  # 내 한채의 이웃
        other_post = publish(self.other, 1)
        self.my_comment = Comment.objects.create(post=other_post, author=self.minju, content="남긴 댓글")
        self.my_sub = Subscription.objects.create(blog=self.other, subscriber=self.minju)
        self.my_like = PostLike.objects.create(post=other_post, user=self.minju)
        self.client.force_login(self.minju)
        self.url = "/api/blogs/minju/demolish"

    def demolish(self, **body):
        return self.client.post(self.url, {"address": "minju", "agree": True, **body}, format="json")

    def test_summary(self):
        self.assertEqual(self.client.get(self.url).json(), {
            "name": "민주의 한채", "address": "minju", "post_count": 1, "draft_count": 1,
            "room_count": 2, "guestbook_count": 1, "subscriber_count": 1,
        })

    def test_needs_owner_address_and_agreement(self):
        reader = APIClient()
        reader.force_login(self.seohyun)
        self.assertEqual(reader.post(self.url, {"address": "minju", "agree": True}, format="json").status_code, 403)
        self.assertEqual(self.demolish(address="minju2").json()["error"]["fields"], {"address": "한채 주소가 맞지 않아요."})
        self.assertEqual(self.demolish(agree=False).status_code, 400)
        self.assertIsNone(Blog.objects.get(pk=self.blog.pk).deleted_at)

    def test_demolish_keeps_account_and_my_things_elsewhere(self):
        self.assertEqual(self.demolish().json(), {"demolished": True})
        blog = Blog.objects.get(pk=self.blog.pk)
        self.assertIsNotNone(blog.deleted_at)
        self.assertEqual(blog.name, "허문 한채")
        self.assertFalse(Post.objects.filter(blog=blog).exists())
        self.assertFalse(Category.objects.filter(blog=blog).exists())
        self.assertFalse(GuestbookEntry.objects.filter(blog=blog).exists())
        self.assertFalse(Subscription.objects.filter(blog=blog).exists())
        # 계정과 다른 한채에 남긴 것은 그대로
        me = self.client.get("/api/auth/me").json()["user"]
        self.assertEqual(me["nickname"], "민주")
        self.assertIsNone(me["blog_address"])
        for obj in (self.my_comment, self.my_sub, self.my_like):
            self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())
        self.assertEqual(APIClient().get("/api/blogs/minju").status_code, 404)

    def test_can_build_again_but_not_with_old_address(self):
        self.demolish()
        self.assertFalse(self.client.get("/api/blogs/address-available", {"address": "minju"}).json()["available"])
        res = self.client.post("/api/blogs", {"address": "minju-new", "name": "새 한채"}, format="json")
        self.assertEqual(res.status_code, 201)

    def test_post_photos_are_deleted_but_profile_photo_kept(self):
        def upload():
            up = self.client.post("/api/images", {"file": SimpleUploadedFile("a.png", png_bytes(), "image/png")}, format="multipart").json()
            return Image.objects.get(pk=up["id"])
        in_post, profile = upload(), upload()
        self.client.post("/api/blogs/minju/posts", {"title": "사진", "content": f'<p><img src="{in_post.file.url}"></p>'}, format="json")
        self.client.patch("/api/me", {"profile_image_id": profile.pk}, format="json")
        with self.captureOnCommitCallbacks(execute=True):
            self.demolish()
        self.assertFalse(Image.objects.filter(pk=in_post.pk).exists())
        self.assertFalse(os.path.exists(os.path.join(settings.MEDIA_ROOT, in_post.file.name)))
        self.assertTrue(Image.objects.filter(pk=profile.pk).exists())
        self.assertTrue(os.path.exists(os.path.join(settings.MEDIA_ROOT, profile.file.name)))
