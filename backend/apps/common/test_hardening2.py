"""운영 다듬기: 화면 파일 요청은 DB 를 쓰지 않는다, CSP 헤더, 한도 · 횟수 제한, 프로필 사진, 댓글 목록 쿼리, 관리 기록."""

import shutil
import tempfile
from importlib import import_module

from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import User
from apps.accounts.tests import make_member
from apps.blogs.demolish import demolish_blogs
from apps.blogs.models import Blog
from apps.community.models import Comment, GuestbookEntry
from apps.moderation.models import AdminLog
from apps.posts.cleanup import unused_images
from apps.posts.models import Category, Image, Post
from apps.posts.tests import png_bytes

TEMP_MEDIA = tempfile.mkdtemp(prefix="hanchae-test-hardening2-")


def tearDownModule():
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


class ScreenFilesDoNotTouchTheDatabaseTests(APITestCase):
    def setUp(self):
        self.minju = make_member()
        self.client.force_login(self.minju)

    def test_logged_in_screen_file_requests_run_no_queries(self):
        for path in ("/", "/login", "/css/hanchae.css", "/js/api.js"):
            with CaptureQueriesContext(connection) as queries:
                res = self.client.get(path)
                b"".join(res.streaming_content)
            self.assertEqual(res.status_code, 200, path)
            self.assertEqual(len(queries), 0, (path, [q["sql"][:80] for q in queries]))

    def test_api_requests_still_keep_the_login_alive(self):
        key = self.client.session.session_key
        Session.objects.filter(pk=key).update(expire_date=timezone.now() + timezone.timedelta(days=1))
        self.client.get("/css/hanchae.css")
        self.assertLess(Session.objects.get(pk=key).expire_date, timezone.now() + timezone.timedelta(days=2))
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["nickname"], "민주")
        # API 요청은 세션을 읽으므로 만료가 다시 2주 뒤로 밀린다
        self.assertGreater(Session.objects.get(pk=key).expire_date, timezone.now() + timezone.timedelta(days=13))

    def test_login_and_logout_still_save_the_session(self):
        client = APIClient()
        res = client.post("/api/auth/login", {"email": "minju@example.com", "password": "hanchae-1234"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIn("sessionid", res.cookies)
        self.assertEqual(client.get("/api/auth/me").json()["user"]["nickname"], "민주")
        client.post("/api/auth/logout")
        self.assertEqual(client.get("/api/auth/me").json(), {"user": None})


class ContentSecurityPolicyTests(APITestCase):
    def test_header_on_screens_and_api_but_not_django_admin(self):
        for path in ("/", "/post?address=minju&no=1", "/api/topics", "/없는-주소", "/api/없는-주소"):
            csp = self.client.get(path).get("Content-Security-Policy", "")
            self.assertIn("script-src 'self'", csp, path)
            self.assertIn("frame-ancestors 'none'", csp, path)
            self.assertNotIn("'unsafe-inline'", csp.split("script-src")[1].split(";")[0], path)
        self.assertNotIn("Content-Security-Policy", self.client.get("/django-admin/"))  # 로그인 화면으로 넘기는 응답

    def test_screens_have_no_inline_script(self):
        """CSP 가 막는 것(인라인 <script> · on… 속성)이 화면 파일에 없어야 한다. 있으면 그 기능이 조용히 멈춘다."""
        import re

        from django.conf import settings

        for page in sorted(settings.FRONTEND_DIR.glob("*.html")):
            html = page.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"<script(?![^>]*\ssrc=)[^>]*>", html), page.name)
            self.assertIsNone(re.search(r"<[^>]+\son[a-z]+\s*=", html), page.name)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class LimitTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.minju = make_member()
        self.blog = Blog.objects.create(owner=self.minju, address="minju", name="민주의 한채", last_post_no=1)
        self.post = Post.objects.create(
            blog=self.blog, post_no=1, title="기록", content="<p>본문</p>", content_text="본문",
            status=Post.Status.PUBLISHED, published_at=timezone.now(),
        )
        self.client.force_login(self.minju)

    def test_rooms_are_capped(self):
        Category.objects.bulk_create([Category(blog=self.blog, name=f"방 {i}", sort_order=i) for i in range(100)])
        res = self.client.post("/api/blogs/minju/categories", {"name": "하나 더"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("100개", res.json()["error"]["message"])

    def test_body_is_capped_at_1mb(self):
        res = self.client.post("/api/blogs/minju/posts", {"title": "긴 글", "content": "<p>" + "a" * 1_000_001 + "</p>"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("너무 길어요", res.json()["error"]["fields"]["content"])

    def test_far_too_big_request_is_answered_in_the_api_shape(self):
        # Django 의 요청 본문 상한(2.5MB)을 넘으면 뷰까지 오지 못한다. 그래도 화면이 읽을 수 있는 JSON 으로 답한다
        res = self.client.post("/api/blogs/minju/posts", {"title": "긴 글", "content": "a" * 3_000_000}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "BAD_REQUEST")
        self.assertIn("너무 커요", res.json()["error"]["message"])

    def test_new_password_is_capped_at_128(self):
        res = self.client.post("/api/me/password", {"current_password": "hanchae-1234", "new_password": "가나다라" * 33}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("128자", res.json()["error"]["fields"]["new_password"])

    def test_search_is_throttled_even_though_it_reads(self):
        visitor = APIClient()
        with self.settings(REST_FRAMEWORK={**self.rest_settings(), "DEFAULT_THROTTLE_RATES": {**self.rest_settings()["DEFAULT_THROTTLE_RATES"], "search": "3/min"}}):
            from rest_framework.settings import api_settings
            from rest_framework.throttling import ScopedRateThrottle

            ScopedRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
            try:
                codes = [visitor.get("/api/search/posts", {"q": "기록"}).status_code for _ in range(4)]
            finally:
                ScopedRateThrottle.THROTTLE_RATES = self.rest_settings()["DEFAULT_THROTTLE_RATES"]
        self.assertEqual(codes, [200, 200, 200, 429])
        # 다른 읽는 요청은 세지 않는다
        self.assertEqual(visitor.get("/api/topics").status_code, 200)

    def rest_settings(self):
        from django.conf import settings

        return settings.REST_FRAMEWORK

    def test_likes_and_subscriptions_have_a_scope(self):
        from apps.community.views import PostLikeView, SubscriptionView
        from django.conf import settings

        for view in (PostLikeView, SubscriptionView):
            self.assertIn(view.throttle_scope, settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ProfilePhotoTests(APITestCase):
    def setUp(self):
        self.minju = make_member()
        self.blog = Blog.objects.create(owner=self.minju, address="minju", name="민주의 한채")
        self.client.force_login(self.minju)

    def upload(self):
        res = self.client.post("/api/images", {"file": SimpleUploadedFile("a.png", png_bytes(), "image/png")}, format="multipart")
        return Image.objects.get(pk=res.json()["id"])

    def test_profile_photo_is_the_small_image(self):
        image = self.upload()
        user = self.client.patch("/api/me", {"profile_image_id": image.pk}, format="json").json()["user"]
        self.assertEqual(user["profile_image_url"], "/media/" + image.thumb_file.name)
        self.assertEqual(self.client.get("/api/blogs/minju").json()["profile_image_url"], "/media/" + image.thumb_file.name)

    def test_cleanup_keeps_photos_linked_either_way(self):
        new_style, old_style, unused = self.upload(), self.upload(), self.upload()
        self.client.patch("/api/me", {"profile_image_id": new_style.pk}, format="json")
        seohyun = make_member("seohyun@example.com", "서현")
        Image.objects.filter(pk=old_style.pk).update(uploader=seohyun)
        User.objects.filter(pk=seohyun.pk).update(profile_image=old_style.file.name)  # 예전에 원본 경로로 건 프로필
        Image.objects.update(created_at=timezone.now() - timezone.timedelta(days=2))
        self.assertEqual(list(unused_images()), [unused])

    def test_demolish_keeps_the_owner_photo(self):
        image = self.upload()
        self.client.patch("/api/me", {"profile_image_id": image.pk}, format="json")
        self.client.post("/api/blogs/minju/posts", {"title": "글", "content": f'<p>사진</p><img src="/media/{image.file.name}">'}, format="json")
        self.minju.refresh_from_db()
        files = demolish_blogs([self.blog], self.minju)
        self.assertEqual(files, [])
        self.assertTrue(Image.objects.filter(pk=image.pk).exists())

    def test_migration_switches_old_profiles_to_the_small_image(self):
        from django.apps import apps as django_apps

        image = self.upload()
        User.objects.filter(pk=self.minju.pk).update(profile_image=image.file.name)
        migration = import_module("apps.accounts.migrations.0004_profile_image_thumb")
        migration.use_thumbs(django_apps, None)
        self.assertEqual(User.objects.get(pk=self.minju.pk).profile_image.name, image.thumb_file.name)
        migration.use_originals(django_apps, None)
        self.assertEqual(User.objects.get(pk=self.minju.pk).profile_image.name, image.file.name)


class ListQueryCountTests(APITestCase):
    """댓글 · 방명록이 늘어도 쿼리 수는 그대로다 (쓴 사람의 한채를 줄마다 묻지 않는다)."""

    def setUp(self):
        self.minju = make_member()
        self.blog = Blog.objects.create(owner=self.minju, address="minju", name="민주의 한채", last_post_no=1)
        self.post = Post.objects.create(
            blog=self.blog, post_no=1, title="기록", content="<p>본문</p>", content_text="본문",
            status=Post.Status.PUBLISHED, published_at=timezone.now(),
        )
        self.writers = []

    def add_writers(self, count):
        start = len(self.writers)
        for i in range(start, start + count):
            user = User.objects.create_user(f"w{i}@example.com", "password123", nickname=f"손님{i}")
            if i % 2 == 0:
                Blog.objects.create(owner=user, address=f"guest-{i}", name=f"손님{i}의 한채")
            Comment.objects.create(post=self.post, author=user, content="댓글")
            GuestbookEntry.objects.create(blog=self.blog, author=user, content="방명록")
            self.writers.append(user)

    def count(self, path):
        with CaptureQueriesContext(connection) as queries:
            res = self.client.get(path)
        self.assertEqual(res.status_code, 200)
        return len(queries), res.json()

    def test_comment_and_guestbook_lists(self):
        self.add_writers(3)
        few_comments, body = self.count("/api/blogs/minju/posts/1/comments")
        few_guestbook, guestbook = self.count("/api/blogs/minju/guestbook")
        self.assertEqual([c["author"]["blog_address"] for c in body["items"]], ["guest-0", None, "guest-2"])
        self.assertEqual(guestbook["items"][0]["author_blog"], {"address": "guest-2", "name": "손님2의 한채"})
        self.assertIsNone(guestbook["items"][1]["author_blog"])

        self.add_writers(6)
        self.assertEqual(self.count("/api/blogs/minju/posts/1/comments")[0], few_comments)
        self.assertEqual(self.count("/api/blogs/minju/guestbook")[0], few_guestbook)


class EverPublicTests(APITestCase):
    def setUp(self):
        self.minju = make_member()
        Blog.objects.create(owner=self.minju, address="minju", name="민주의 한채")
        self.client.force_login(self.minju)

    def publish(self, **extra):
        res = self.client.post("/api/blogs/minju/posts", {"title": "글", "content": "<p>본문</p>", **extra}, format="json")
        return Post.objects.get(blog__address="minju", post_no=res.json()["no"])

    def test_follows_the_publishing_rule(self):
        self.assertTrue(self.publish().ever_public)
        private = self.publish(visibility="PRIVATE")
        self.assertFalse(private.ever_public)
        self.assertFalse(self.publish(visibility="SUBSCRIBERS").ever_public)

        self.client.patch(f"/api/blogs/minju/posts/{private.post_no}", {"visibility": "PUBLIC"}, format="json")
        private.refresh_from_db()
        self.assertTrue(private.ever_public)
        self.client.patch(f"/api/blogs/minju/posts/{private.post_no}", {"visibility": "PRIVATE"}, format="json")
        private.refresh_from_db()
        self.assertTrue(private.ever_public)  # 한 번 공개됐던 것은 그대로

    def test_draft_is_not_public_until_published(self):
        draft_id = self.client.post("/api/blogs/minju/drafts", {"title": "쓰는 중"}, format="json").json()["id"]
        self.assertFalse(Post.objects.get(pk=draft_id).ever_public)
        self.client.patch(f"/api/blogs/minju/drafts/{draft_id}", {"visibility": "PRIVATE"}, format="json")
        self.client.post(f"/api/blogs/minju/drafts/{draft_id}/publish", {"title": "다 썼다", "content": "<p>본문</p>"}, format="json")
        self.assertFalse(Post.objects.get(pk=draft_id).ever_public)  # 나만 보기로 발행했다

    def test_migration_clears_drafts(self):
        from django.apps import apps as django_apps

        draft_id = self.client.post("/api/blogs/minju/drafts", {"title": "쓰는 중"}, format="json").json()["id"]
        published = self.publish()
        Post.objects.update(ever_public=True)
        import_module("apps.posts.migrations.0003_drafts_never_public").fix_drafts(django_apps, None)
        self.assertFalse(Post.objects.get(pk=draft_id).ever_public)
        self.assertTrue(Post.objects.get(pk=published.pk).ever_public)


class AdminLogListTests(APITestCase):
    def setUp(self):
        self.admin = make_member("admin@example.com", "관리인")
        User.objects.filter(pk=self.admin.pk).update(role="ADMIN")
        self.minju = make_member()
        self.blog = Blog.objects.create(owner=self.minju, address="minju", name="민주의 한채", last_post_no=1)
        self.post = Post.objects.create(
            blog=self.blog, post_no=1, title="광고 글", content="<p>본문</p>", content_text="본문",
            status=Post.Status.PUBLISHED, published_at=timezone.now(),
        )
        self.comment = Comment.objects.create(post=self.post, author=self.minju, content="도배 댓글")
        self.client.force_login(self.admin)

    def test_lists_actions_newest_first_with_targets(self):
        self.client.post(f"/api/admin/posts/{self.post.pk}/hide", {"reason": "광고"}, format="json")
        self.client.post(f"/api/admin/comments/{self.comment.pk}/hide", {"reason": "도배"}, format="json")
        self.client.post(f"/api/admin/users/{self.minju.pk}/sanctions", {"reason": "되풀이", "ends_at": None}, format="json")
        body = self.client.get("/api/admin/logs").json()
        self.assertEqual(body["total"], 3)
        self.assertEqual([i["action"] for i in body["items"]], ["SANCTION_USER", "HIDE_COMMENT", "HIDE_POST"])
        sanction, comment, post = body["items"]
        self.assertEqual((sanction["admin"], sanction["reason"]), ("관리인", "되풀이"))
        self.assertEqual(sanction["target"], {"nickname": "민주", "withdrawn": False})
        self.assertEqual(comment["target"], {"content": "도배 댓글", "blog_address": "minju", "no": 1})
        self.assertEqual(post["target"], {"title": "광고 글", "blog_address": "minju", "no": 1})

        self.assertEqual([i["reason"] for i in self.client.get("/api/admin/logs", {"q": "도배"}).json()["items"]], ["도배"])

    def test_deleted_target_is_null_and_log_stays(self):
        self.client.post(f"/api/admin/comments/{self.comment.pk}/hide", {"reason": "도배"}, format="json")
        self.comment.delete()
        item = self.client.get("/api/admin/logs").json()["items"][0]
        self.assertIsNone(item["target"])
        self.assertEqual(AdminLog.objects.count(), 1)

    def test_only_service_admin(self):
        self.assertEqual(APIClient().get("/api/admin/logs").status_code, 401)
        member = APIClient()
        member.force_login(self.minju)
        self.assertEqual(member.get("/api/admin/logs").status_code, 403)
