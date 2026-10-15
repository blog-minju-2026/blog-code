"""마을 관리 API (ADMIN-01 · 02 · 03, 명세 contracts/pages.md 관리 영역 · data-model 6절)."""

from datetime import timedelta

from django.contrib import admin
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import User
from apps.blogs.models import Blog
from apps.community.models import Comment, GuestbookEntry
from apps.posts.models import Post

from .models import AdminLog, UserSanction


class AdminTestBase(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin@example.com", "password123", nickname="관리인", role="ADMIN")
        self.owner = User.objects.create_user("minju@example.com", "password123", nickname="민주")
        self.reader = User.objects.create_user("seohyun@example.com", "password123", nickname="서현")
        self.blog = Blog.objects.create(owner=self.owner, address="minju", name="민주의 한채", last_post_no=2)
        self.post = self.make_post(1, Post.Visibility.PUBLIC, "봄 소풍")
        self.secret = self.make_post(2, Post.Visibility.PRIVATE, "나만 보는 기록")
        self.comment = Comment.objects.create(post=self.post, author=self.reader, content="잘 봤어요")
        self.entry = GuestbookEntry.objects.create(blog=self.blog, author=self.reader, content="놀러 왔어요")

        self.client.force_authenticate(self.admin)
        self.guest = APIClient()
        self.member = APIClient()
        self.member.force_authenticate(self.reader)
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(self.owner)

    def make_post(self, no, visibility, title):
        return Post.objects.create(
            blog=self.blog, post_no=no, title=title, content="<p>본문</p>", content_text="본문",
            status=Post.Status.PUBLISHED, published_at=timezone.now(), visibility=visibility,
        )


class AdminAccessTests(AdminTestBase):
    def test_only_service_admin(self):
        for url in ["/api/admin/users", "/api/admin/posts", "/api/admin/comments", "/api/admin/guestbook"]:
            self.assertEqual(self.guest.get(url).status_code, 401, url)
            self.assertEqual(self.member.get(url).status_code, 403, url)
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_change_requests_also_need_admin(self):
        res = self.member.post(f"/api/admin/posts/{self.post.pk}/hide", {"reason": "스팸"}, format="json")
        self.assertEqual(res.status_code, 403)
        self.assertIsNone(Post.objects.get(pk=self.post.pk).hidden_at)


class SanctionTests(AdminTestBase):
    def sanction(self, user, **body):
        body.setdefault("reason", "스팸 댓글 반복")
        return self.client.post(f"/api/admin/users/{user.pk}/sanctions", body, format="json")

    def test_search_users(self):
        res = self.client.get("/api/admin/users", {"q": "민주"})
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertEqual([u["nickname"] for u in items], ["민주"])
        self.assertEqual(items[0]["blog"], {"address": "minju", "name": "민주의 한채"})
        self.assertIsNone(items[0]["sanction"])
        # 이메일로도 찾는다
        self.assertEqual(self.client.get("/api/admin/users", {"q": "seohyun@"}).json()["items"][0]["nickname"], "서현")

    def test_sanction_with_end_date(self):
        ends = timezone.now() + timedelta(days=7)
        res = self.sanction(self.owner, ends_at=ends.isoformat())
        self.assertEqual(res.status_code, 201)
        sanction = UserSanction.objects.get(user=self.owner)
        self.assertEqual(sanction.admin, self.admin)
        self.assertEqual(sanction.reason, "스팸 댓글 반복")
        self.assertAlmostEqual(sanction.ends_at.timestamp(), ends.timestamp(), delta=1)

        log = AdminLog.objects.get()
        self.assertEqual((log.action, log.target_type, log.target_id), ("SANCTION_USER", "user", self.owner.pk))

        # 제한 중인 회원의 한채는 다른 사람에게 없는 곳이 된다
        self.assertEqual(self.member.get("/api/blogs/minju").status_code, 404)
        user = self.client.get("/api/admin/users", {"q": "민주"}).json()["items"][0]
        self.assertEqual(user["sanction"]["reason"], "스팸 댓글 반복")

    def test_permanent_sanction(self):
        self.assertEqual(self.sanction(self.owner, ends_at=None).status_code, 201)
        self.assertIsNone(UserSanction.objects.get(user=self.owner).ends_at)

    def test_reason_and_future_end_required(self):
        res = self.sanction(self.owner, reason=" ", ends_at=None)
        self.assertEqual(res.status_code, 400)
        self.assertIn("reason", res.json()["error"]["fields"])
        res = self.sanction(self.owner, ends_at=(timezone.now() - timedelta(days=1)).isoformat())
        self.assertEqual(res.status_code, 400)
        self.assertIn("ends_at", res.json()["error"]["fields"])
        # ends_at 을 아예 빼면 영구인지 실수인지 알 수 없으니 받지 않는다
        res = self.client.post(f"/api/admin/users/{self.owner.pk}/sanctions", {"reason": "사유"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(UserSanction.objects.exists())

    def test_cannot_sanction_admin_or_self(self):
        other_admin = User.objects.create_user("admin2@example.com", "password123", nickname="관리인2", role="ADMIN")
        self.assertEqual(self.sanction(other_admin, ends_at=None).status_code, 403)
        self.assertEqual(self.sanction(self.admin, ends_at=None).status_code, 403)
        self.assertFalse(UserSanction.objects.exists())

    def test_already_sanctioned_conflict(self):
        self.sanction(self.owner, ends_at=None)
        self.assertEqual(self.sanction(self.owner, ends_at=None).status_code, 409)

    def test_release(self):
        self.sanction(self.owner, ends_at=None)
        res = self.client.post(f"/api/admin/users/{self.owner.pk}/release", {"reason": "소명 확인"}, format="json")
        self.assertEqual(res.status_code, 200)
        sanction = UserSanction.objects.get(user=self.owner)
        self.assertIsNotNone(sanction.released_at)
        self.assertEqual(sanction.released_by, self.admin)
        self.assertEqual(self.member.get("/api/blogs/minju").status_code, 200)
        self.assertEqual(list(AdminLog.objects.values_list("action", flat=True)), ["RELEASE_USER", "SANCTION_USER"])

    def test_release_needs_active_sanction_and_reason(self):
        url = f"/api/admin/users/{self.owner.pk}/release"
        self.assertEqual(self.client.post(url, {"reason": "해제"}, format="json").status_code, 409)
        self.sanction(self.owner, ends_at=None)
        self.assertEqual(self.client.post(url, {"reason": ""}, format="json").status_code, 400)

    def test_unknown_user(self):
        self.assertEqual(self.client.post("/api/admin/users/999999/sanctions", {"reason": "x", "ends_at": None}, format="json").status_code, 404)


class SuspendedSessionTests(AdminTestBase):
    """로그인한 채로 제한되면 다음 요청부터 막는다 (data-model 6절)."""

    def test_logged_in_member_is_logged_out_on_next_request(self):
        session = APIClient()
        session.force_login(self.owner)  # 세션 쿠키로 로그인 (미들웨어를 거친다)
        self.assertEqual(session.get("/api/auth/me").json()["user"]["nickname"], "민주")

        UserSanction.objects.create(user=self.owner, admin=self.admin, reason="도배", starts_at=timezone.now())
        res = session.post("/api/blogs/minju/posts", {"title": "t", "content": "<p>b</p>"}, format="json")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"]["code"], "SUSPENDED")
        self.assertEqual(res.json()["error"]["detail"]["reason"], "도배")
        self.assertFalse(Post.objects.filter(title="t").exists())

        # 세션이 끊겼으므로 그다음은 비회원
        self.assertEqual(session.get("/api/auth/me").json(), {"user": None})

    def test_pages_still_open_after_logout(self):
        session = APIClient()
        session.force_login(self.owner)
        UserSanction.objects.create(user=self.owner, admin=self.admin, reason="도배", starts_at=timezone.now())
        self.assertNotEqual(session.get("/").status_code, 403)
        self.assertEqual(session.get("/api/auth/me").json(), {"user": None})


class HidePostTests(AdminTestBase):
    def hide(self, post, reason="광고 글"):
        return self.client.post(f"/api/admin/posts/{post.pk}/hide", {"reason": reason}, format="json")

    def test_search_posts_includes_private_and_hidden(self):
        res = self.client.get("/api/admin/posts", {"q": "기록"})
        self.assertEqual([p["title"] for p in res.json()["items"]], ["나만 보는 기록"])
        item = res.json()["items"][0]
        self.assertEqual(item["blog"]["address"], "minju")
        self.assertEqual(item["author"]["nickname"], "민주")
        self.assertIsNone(item["hidden"])
        # 블로그 주소로도 찾는다
        self.assertEqual(len(self.client.get("/api/admin/posts", {"q": "minju"}).json()["items"]), 2)

    def test_drafts_are_not_listed(self):
        Post.objects.create(blog=self.blog, title="쓰다 만 글", content="<p>x</p>", content_text="x")
        titles = [p["title"] for p in self.client.get("/api/admin/posts").json()["items"]]
        self.assertNotIn("쓰다 만 글", titles)

    def test_detail_shows_body_and_comments(self):
        res = self.client.get(f"/api/admin/posts/{self.secret.pk}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["content"], "<p>본문</p>")
        res = self.client.get(f"/api/admin/posts/{self.post.pk}")
        self.assertEqual(res.json()["comments"][0]["content"], "잘 봤어요")

    def test_hide_and_unhide(self):
        res = self.hide(self.post)
        self.assertEqual(res.status_code, 200)
        post = Post.objects.get(pk=self.post.pk)
        self.assertEqual((post.hidden_reason, post.hidden_by), ("광고 글", self.admin))
        self.assertIsNotNone(post.hidden_at)

        # 다른 사람에게는 없는 기록, 주인에게는 숨김 사실과 사유가 보인다
        self.assertEqual(self.member.get("/api/blogs/minju/posts/1").status_code, 404)
        mine = self.owner_client.get("/api/blogs/minju/posts/1").json()
        self.assertEqual(mine["hidden"]["reason"], "광고 글")
        listed = self.owner_client.get("/api/blogs/minju/posts").json()["items"]
        self.assertEqual([p["hidden"]["reason"] if p["hidden"] else None for p in listed], [None, "광고 글"])
        self.make_post(3, Post.Visibility.PUBLIC, "숨기지 않은 기록")
        others = self.member.get("/api/blogs/minju/posts").json()["items"]
        self.assertEqual([p["no"] for p in others], [3])
        self.assertNotIn("hidden", others[0])  # 숨김 정보는 주인에게만

        res = self.client.post(f"/api/admin/posts/{self.post.pk}/unhide", {"reason": "오해였어요"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(Post.objects.get(pk=self.post.pk).hidden_at)
        self.assertEqual(self.member.get("/api/blogs/minju/posts/1").status_code, 200)
        self.assertEqual(list(AdminLog.objects.values_list("action", flat=True)), ["UNHIDE_POST", "HIDE_POST"])

    def test_hide_rules(self):
        self.assertEqual(self.hide(self.post, reason="").status_code, 400)
        self.assertEqual(self.hide(self.post, reason="가" * 201).status_code, 400)
        self.assertEqual(self.hide(self.post).status_code, 200)
        self.assertEqual(self.hide(self.post).status_code, 409)
        self.assertEqual(self.client.post(f"/api/admin/posts/{self.secret.pk}/unhide", {"reason": "x"}, format="json").status_code, 409)
        self.assertEqual(self.client.post("/api/admin/posts/999999/hide", {"reason": "x"}, format="json").status_code, 404)

    def test_owner_edit_keeps_hidden(self):
        self.hide(self.post)
        res = self.owner_client.patch("/api/blogs/minju/posts/1", {"title": "고친 제목"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(Post.objects.get(pk=self.post.pk).hidden_at)


class HideCommentTests(AdminTestBase):
    def test_hide_comment(self):
        res = self.client.post(f"/api/admin/comments/{self.comment.pk}/hide", {"reason": "욕설"}, format="json")
        self.assertEqual(res.status_code, 200)
        items = self.member.get("/api/blogs/minju/posts/1/comments").json()["items"]
        self.assertEqual((items[0]["hidden"], items[0]["content"]), (True, None))

        self.client.post(f"/api/admin/comments/{self.comment.pk}/unhide", {"reason": "되돌림"}, format="json")
        self.assertIsNone(Comment.objects.get(pk=self.comment.pk).hidden_at)
        self.assertEqual(list(AdminLog.objects.values_list("action", flat=True)), ["UNHIDE_COMMENT", "HIDE_COMMENT"])

    def test_hide_guestbook(self):
        res = self.client.post(f"/api/admin/guestbook/{self.entry.pk}/hide", {"reason": "도배"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(GuestbookEntry.objects.get(pk=self.entry.pk).hidden_reason, "도배")
        self.assertEqual(AdminLog.objects.get().target_type, "guestbook")

    def test_search_comments_and_guestbook(self):
        res = self.client.get("/api/admin/comments", {"q": "잘 봤"})
        item = res.json()["items"][0]
        self.assertEqual((item["content"], item["author"]["nickname"]), ("잘 봤어요", "서현"))
        self.assertEqual(item["post"], {"id": self.post.pk, "title": "봄 소풍", "blog_address": "minju", "no": 1})
        res = self.client.get("/api/admin/guestbook", {"q": "서현"})
        self.assertEqual(res.json()["items"][0]["blog"]["address"], "minju")


class AdminLogTests(AdminTestBase):
    def test_logs_cannot_be_changed_or_deleted(self):
        log = AdminLog.objects.create(admin=self.admin, action="HIDE_POST", target_type="post", target_id=1, reason="x")
        log.reason = "바꿈"
        with self.assertRaises(PermissionError), transaction.atomic():
            log.save()
        with self.assertRaises(PermissionError), transaction.atomic():
            log.delete()
        with self.assertRaises(PermissionError), transaction.atomic():
            AdminLog.objects.filter(pk=log.pk).update(reason="몰래")
        with self.assertRaises(PermissionError), transaction.atomic():
            AdminLog.objects.filter(pk=log.pk).delete()
        self.assertEqual(AdminLog.objects.get(pk=log.pk).reason, "x")


class DjangoAdminTests(APITestCase):
    """/django-admin/ 에는 글 · 댓글 · 방명록을 두지 않는다 (contracts/pages.md, ADMIN-01a)."""

    def test_content_models_are_not_registered(self):
        for model in (Post, Comment, GuestbookEntry):
            self.assertNotIn(model, admin.site._registry, model.__name__)

    def test_moderation_records_are_read_only(self):
        request = type("Request", (), {})()
        for model in (UserSanction, AdminLog):
            model_admin = admin.site._registry[model]
            self.assertFalse(model_admin.has_add_permission(request), model.__name__)
            self.assertFalse(model_admin.has_change_permission(request), model.__name__)
            self.assertFalse(model_admin.has_delete_permission(request), model.__name__)
