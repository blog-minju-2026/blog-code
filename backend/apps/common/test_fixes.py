"""기능 오류 고치기: 쓰이지 않는 사진 정리 · 정기 정리 명령 · 이상한 쿼리 값 · 본문 사진 주소 · 이용 제한된 한채의 댓글."""

import os
import shutil
import tempfile
from datetime import timedelta
from io import StringIO

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.serializers import user_summary
from apps.accounts.tests import make_member
from apps.blogs.models import Blog
from apps.community.models import Comment
from apps.moderation.models import UserSanction
from apps.posts.cleanup import delete_unused_images
from apps.posts.content import sanitize
from apps.posts.models import Image, Post, PostView
from apps.posts.tests import png_bytes

TEMP_MEDIA = tempfile.mkdtemp(prefix="hanchae-test-fixes-")


def tearDownModule():
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class UnusedImageCleanupTests(APITestCase):
    def setUp(self):
        self.minju = make_member()
        self.blog = Blog.objects.create(owner=self.minju, address="minju", name="민주의 한채")
        self.client.force_login(self.minju)

    def upload(self):
        res = self.client.post("/api/images", {"file": SimpleUploadedFile("a.png", png_bytes(), "image/png")}, format="multipart")
        return Image.objects.get(pk=res.json()["id"])

    def files(self, image):
        return [os.path.join(settings.MEDIA_ROOT, image.file.name), os.path.join(settings.MEDIA_ROOT, image.thumb_file.name)]

    def age(self, *images, hours=25):
        Image.objects.filter(pk__in=[i.pk for i in images]).update(created_at=timezone.now() - timedelta(hours=hours))

    def test_only_old_unused_images_are_deleted_with_files(self):
        unused, fresh, in_post, profile, blog_photo = (self.upload() for _ in range(5))
        self.client.post("/api/blogs/minju/posts", {"title": "글", "content": f'<p>사진</p><img src="{in_post.file.url}">', "topic_slug": None}, format="json")
        self.client.patch("/api/me", {"profile_image_id": profile.pk}, format="json")
        self.client.patch("/api/blogs/minju", {"profile_image_id": blog_photo.pk}, format="json")
        self.age(unused, in_post, profile, blog_photo)  # fresh 는 방금 올린 것

        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(delete_unused_images(), 1)
        self.assertFalse(Image.objects.filter(pk=unused.pk).exists())
        self.assertFalse(any(os.path.exists(p) for p in self.files(unused)))
        for kept in (fresh, in_post, profile, blog_photo):
            self.assertTrue(Image.objects.filter(pk=kept.pk).exists())
            self.assertTrue(all(os.path.exists(p) for p in self.files(kept)))

    def test_maintenance_command_runs_every_cleanup(self):
        unused = self.upload()
        self.age(unused)
        post = Post.objects.create(blog=self.blog, post_no=1, content="x", content_text="x", status="PUBLISHED", published_at=timezone.now())
        PostView.objects.create(post=post, viewer_key="old", viewed_at=timezone.now() - timedelta(days=40))
        PostView.objects.create(post=post, viewer_key="new", viewed_at=timezone.now())

        out = StringIO()
        call_command("run_maintenance", dry_run=True, stdout=out)
        self.assertIn("쓰이지 않는 사진 1개", out.getvalue())
        self.assertTrue(Image.objects.filter(pk=unused.pk).exists())  # dry-run 은 지우지 않는다

        call_command("run_maintenance", stdout=StringIO())
        self.assertFalse(Image.objects.filter(pk=unused.pk).exists())
        self.assertEqual(list(PostView.objects.values_list("viewer_key", flat=True)), ["new"])


class OddQueryValueTests(APITestCase):
    def setUp(self):
        Blog.objects.create(owner=make_member(), address="minju", name="민주의 한채")

    def test_unicode_digit_and_huge_numbers_do_not_crash(self):
        for query in ("category=²", "category=99999999999999999999999", "page=100000000000000000000000"):
            res = self.client.get(f"/api/blogs/minju/posts?{query}")
            self.assertLess(res.status_code, 500, query)


class SanitizeMediaPathTests(APITestCase):
    def test_paths_leaving_media_are_dropped(self):
        for src in ("/media/../api/auth/me", "/media/%2e%2e/api/auth/me", "/media/images/../../x", "/media//x.png"):
            self.assertNotIn("<img", sanitize(f'<p>a</p><img src="{src}">'), src)
        self.assertIn('src="/media/images/2026/10/a.png"', sanitize('<img src="/media/images/2026/10/a.png">'))


class SanctionedBlogCommentTests(APITestCase):
    def setUp(self):
        self.owner = make_member()
        self.reader = make_member(email="seohyun@example.com", nickname="서현")
        admin = make_member(email="admin@example.com", nickname="관리인")
        blog = Blog.objects.create(owner=self.owner, address="minju", name="민주의 한채")
        post = Post.objects.create(blog=blog, post_no=1, content="x", content_text="x", status="PUBLISHED", published_at=timezone.now())
        self.comment = Comment.objects.create(post=post, author=self.reader, content="댓글")
        Blog.objects.create(owner=self.reader, address="seohyun", name="서현의 한채")
        UserSanction.objects.create(user=self.owner, admin=admin, reason="도배", starts_at=timezone.now())
        self.sanctioned_reader = self.reader

    def test_comments_on_closed_blog_cannot_be_changed(self):
        self.client.force_login(self.reader)
        res = self.client.patch(f"/api/comments/{self.comment.pk}", {"content": "고침"}, format="json")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self.client.delete(f"/api/comments/{self.comment.pk}").status_code, 404)

    def test_author_link_skips_closed_blog(self):
        self.assertIsNone(user_summary(self.owner, None)["blog_address"])
        self.assertEqual(user_summary(self.reader, None)["blog_address"], "seohyun")


class MaintenanceLogPrivacyTests(APITestCase):
    """정리 명령의 출력은 공개 Actions 로그에 남는다. 개수만 쓰고 이메일 · 닉네임은 쓰지 않는다."""

    def test_output_has_counts_but_no_personal_data(self):
        pending = make_member(email="pending-person@example.com", nickname="숨길닉네임", verified=False)
        old = timezone.now() - timedelta(days=30)
        type(pending).objects.filter(pk=pending.pk).update(created_at=old)

        for dry_run in (True, False):
            out = StringIO()
            call_command("run_maintenance", dry_run=dry_run, stdout=out)
            text = out.getvalue()
            self.assertIn("인증 안 마친 가입 1개", text)
            self.assertNotIn("pending-person", text)
            self.assertNotIn("@", text)
            self.assertNotIn("숨길닉네임", text)
        self.assertFalse(type(pending).objects.filter(pk=pending.pk).exists())

