"""탈퇴 (AUTH-06): GET · POST /api/me/leave."""

import os
import shutil
import tempfile

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.blogs.models import Blog
from apps.community.models import Comment, GuestbookEntry, PostLike, Subscription
from apps.posts.models import Category, Image, Post
from apps.posts.tests import png_bytes

from .models import User
from .test_social import AGREE, come_back_from_provider, kakao_login, social_settings
from .tests import SIGNUP, make_member

TEMP_MEDIA = tempfile.mkdtemp(prefix="hanchae-test-leave-")
PASSWORD = "hanchae-1234"


def tearDownModule():
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


def publish(blog, no, **extra):
    return Post.objects.create(
        blog=blog, post_no=no, content="x", content_text="x", status="PUBLISHED", published_at=timezone.now(), **extra
    )


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class LeaveTests(APITestCase):
    def setUp(self):
        self.minju = make_member()
        self.seohyun = make_member(email="seohyun@example.com", nickname="서현")
        self.blog = Blog.objects.create(owner=self.minju, address="minju", name="민주의 한채")
        self.other_blog = Blog.objects.create(owner=self.seohyun, address="seohyun", name="서현의 한채")

        self.my_post = publish(self.blog, 1)
        Post.objects.create(blog=self.blog, content="x", content_text="x")  # 임시저장도 함께 사라진다
        top = Category.objects.create(blog=self.blog, name="여행")
        Category.objects.create(blog=self.blog, name="제주", parent=top)
        self.other_post = publish(self.other_blog, 1)

        # 다른 한채에 남긴 것 (남는다) · 내 한채 안의 것 (사라진다)
        self.comment_elsewhere = Comment.objects.create(post=self.other_post, author=self.minju, content="잘 봤어요")
        Comment.objects.create(post=self.my_post, author=self.minju, content="내 글에 단 댓글")
        Comment.objects.create(post=self.my_post, author=self.seohyun, content="서현이 내 글에 단 댓글")
        self.guestbook_elsewhere = GuestbookEntry.objects.create(blog=self.other_blog, author=self.minju, content="놀러 왔어요")
        GuestbookEntry.objects.create(blog=self.blog, author=self.seohyun, content="받은 방명록")
        Subscription.objects.create(blog=self.blog, subscriber=self.seohyun)  # 내 한채의 이웃
        Subscription.objects.create(blog=self.other_blog, subscriber=self.minju)  # 내가 맺은 이웃
        PostLike.objects.create(post=self.other_post, user=self.minju)

        self.client.force_login(self.minju)

    def leave(self, client=None, **body):
        return (client or self.client).post("/api/me/leave", {"agree": True, **body}, format="json")

    def test_summary_counts_what_goes_and_what_stays(self):
        self.assertEqual(
            self.client.get("/api/me/leave").json(),
            {
                "can_leave": True,
                "nickname": "민주",
                "confirm_with": "password",
                "social_provider": None,
                "blog": {"name": "민주의 한채", "address": "minju"},
                "post_count": 2,
                "subscriber_count": 1,
                "comment_count": 1,
                "guestbook_count": 1,
            },
        )

    def test_needs_login_password_and_agreement(self):
        self.assertEqual(APIClient().get("/api/me/leave").status_code, 401)

        res = self.leave(password="wrong-password")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["fields"], {"password": "비밀번호가 맞지 않아요."})

        res = self.leave(password=PASSWORD, agree=False)
        self.assertEqual(res.status_code, 400)
        self.assertIn("agree", res.json()["error"]["fields"])

        self.minju.refresh_from_db()
        self.assertTrue(self.minju.is_active)
        self.assertEqual(Post.objects.filter(blog=self.blog).count(), 2)

    def test_leave_removes_my_things_and_keeps_comments_elsewhere(self):
        other_device = APIClient()
        other_device.force_login(self.minju)

        res = self.leave(password=PASSWORD)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"left": True})
        self.assertIsNone(self.client.get("/api/auth/me").json()["user"])
        self.assertIsNone(other_device.get("/api/auth/me").json()["user"])  # 다른 기기도 끊긴다

        user = User.objects.get(pk=self.minju.pk)
        self.assertFalse(user.is_active)
        self.assertIsNone(user.email)
        self.assertIsNone(user.nickname)
        self.assertFalse(user.has_usable_password())
        self.assertIsNotNone(user.withdrawn_at)
        self.assertFalse(EmailAddress.objects.filter(user=user).exists())

        # 내 한채: 기록 · 방 · 받은 방명록 · 이웃이 사라지고, 행은 '허문 한채'로 주소만 예약한다
        self.assertFalse(Post.objects.filter(blog=self.blog).exists())
        self.assertFalse(Category.objects.filter(blog=self.blog).exists())
        self.assertFalse(GuestbookEntry.objects.filter(blog=self.blog).exists())
        self.assertFalse(Subscription.objects.filter(blog=self.blog).exists())
        blog = Blog.objects.get(pk=self.blog.pk)
        self.assertIsNotNone(blog.deleted_at)
        self.assertEqual(blog.name, "허문 한채")
        self.assertEqual(self.client.get("/api/blogs/minju").status_code, 404)

        # 내가 한 것: 맺은 이웃 · 공감은 사라지고, 다른 한채에 남긴 댓글 · 방명록은 '떠난 사람'으로 남는다
        self.assertFalse(Subscription.objects.filter(subscriber=user).exists())
        self.assertFalse(PostLike.objects.filter(user=user).exists())
        self.assertTrue(Comment.objects.filter(pk=self.comment_elsewhere.pk).exists())
        self.assertTrue(GuestbookEntry.objects.filter(pk=self.guestbook_elsewhere.pk).exists())
        comments = self.client.get("/api/blogs/seohyun/posts/1/comments").json()["items"]
        self.assertTrue(comments[0]["author"]["withdrawn"])
        self.assertIsNone(comments[0]["author"]["nickname"])

        # 같은 이메일 · 닉네임으로 다시 가입할 수 있다. 예전 비밀번호로는 로그인할 수 없다
        login = self.client.post("/api/auth/login", {"email": "minju@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(login.status_code, 401)
        self.assertEqual(self.client.post("/api/auth/signup", SIGNUP, format="json").status_code, 201)

    def test_uploaded_photos_are_deleted_with_files(self):
        up = self.client.post(
            "/api/images", {"file": SimpleUploadedFile("a.png", png_bytes(), "image/png")}, format="multipart"
        ).json()
        self.client.patch("/api/me", {"profile_image_id": up["id"]}, format="json")
        image = Image.objects.get(pk=up["id"])
        paths = [os.path.join(settings.MEDIA_ROOT, image.file.name), os.path.join(settings.MEDIA_ROOT, image.thumb_file.name)]
        self.assertTrue(all(os.path.exists(p) for p in paths))

        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.leave(password=PASSWORD).status_code, 200)
        self.assertFalse(Image.objects.filter(pk=up["id"]).exists())
        self.assertFalse(any(os.path.exists(p) for p in paths))

    def test_village_keeper_cannot_leave(self):
        User.objects.filter(pk=self.minju.pk).update(role=User.Role.ADMIN)
        self.assertFalse(self.client.get("/api/me/leave").json()["can_leave"])  # 창을 열 때 바로 알린다
        res = self.leave(password=PASSWORD)
        self.assertEqual(res.status_code, 403)
        self.assertTrue(User.objects.get(pk=self.minju.pk).is_active)


@social_settings
class SocialLeaveTests(APITestCase):
    def setUp(self):
        come_back_from_provider(self.client, kakao_login())
        self.client.post("/api/auth/social/signup", {"nickname": "민주", **AGREE}, format="json")

    def test_social_member_confirms_with_nickname_and_can_come_back(self):
        summary = self.client.get("/api/me/leave").json()
        self.assertEqual(summary["confirm_with"], "nickname")
        self.assertEqual(summary["social_provider"], "카카오")
        self.assertIsNone(summary["blog"])

        res = self.client.post("/api/me/leave", {"nickname": "민지", "agree": True}, format="json")
        self.assertEqual(res.json()["error"]["fields"], {"nickname": "닉네임이 맞지 않아요."})

        res = self.client.post("/api/me/leave", {"nickname": "민주", "agree": True}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(SocialAccount.objects.exists())

        # 같은 카카오 계정으로 오면 새로 가입한다 (예전 계정으로 들어가지 않는다)
        res = come_back_from_provider(self.client, kakao_login())
        self.assertEqual(res["Location"], "/accounts/social/signup/")
        res = self.client.post("/api/auth/social/signup", {"nickname": "민주", **AGREE}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(User.objects.filter(is_active=True).count(), 1)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class LeaveFrontendRequestTests(APITestCase):
    """화면(js/store.js 의 leave)이 보내는 그대로: CSRF 검사를 켜고 X-CSRFToken 헤더로."""

    def test_leave_needs_csrf_header(self):
        make_member()
        client = APIClient(enforce_csrf_checks=True)
        client.post("/api/auth/login", {"email": "minju@example.com", "password": PASSWORD}, format="json",
                    HTTP_X_CSRFTOKEN=self._token(client))
        token = self._token(client)  # 로그인하면 토큰이 바뀐다
        body = {"password": PASSWORD, "agree": True}
        self.assertEqual(client.post("/api/me/leave", body, format="json").status_code, 403)
        res = client.post("/api/me/leave", body, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(client.get("/api/auth/me").json()["user"])

    def _token(self, client):
        client.get("/api/auth/csrf")
        return client.cookies["csrftoken"].value
