"""보안 다듬기: 네이버 이메일 자동 연결 막기, 조회 수 부풀리기 막기, 운영 화면 로그인 횟수 제한."""

from django.test import override_settings
from django.urls import include, path
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import User
from apps.accounts.test_social import AGREE, come_back_from_provider, kakao_login
from apps.accounts.tests import make_member
from apps.blogs.models import Blog
from apps.posts.models import Post
from config import urls as site_urls
from config.urls import social_login_patterns

PROVIDERS = ["kakao", "naver"]
urlpatterns = [path("accounts/", include(social_login_patterns(PROVIDERS)))] + site_urls.urlpatterns
naver_settings = override_settings(
    ROOT_URLCONF=__name__,
    SOCIAL_PROVIDERS=PROVIDERS,
    SOCIALACCOUNT_PROVIDERS={p: {"APPS": [{"client_id": f"{p}-id", "secret": f"{p}-secret"}]} for p in PROVIDERS},
)


def naver_login(uid="n-1", email="minju@example.com", nickname="네이버민주"):
    return {"provider": "naver", "data": {"id": uid, "email": email, "nickname": nickname}, "next": "/"}


@naver_settings
class NaverEmailTests(APITestCase):
    """네이버는 이메일을 확인했는지 알려 주지 않는다 (allauth 가 늘 '인증됨'으로 표시)."""

    def test_naver_email_does_not_log_into_existing_member(self):
        member = make_member(email="minju@example.com", nickname="민주")
        res = come_back_from_provider(self.client, naver_login())
        self.assertEqual(res["Location"], "/accounts/social/signup/")  # 기존 회원으로 들어가지 않는다
        self.assertIsNone(self.client.get("/api/auth/me").json()["user"])
        self.assertFalse(member.socialaccount_set.exists())

        res = self.client.post("/api/auth/social/signup", {"nickname": "네이버민주", **AGREE}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertIn("email", res.json()["error"]["fields"])

    def test_naver_email_does_not_remove_pending_signup(self):
        pending = make_member(email="minju@example.com", nickname="먼저온이", verified=False)
        come_back_from_provider(self.client, naver_login())
        res = self.client.post("/api/auth/social/signup", {"nickname": "네이버민주", **AGREE}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertTrue(User.objects.filter(pk=pending.pk).exists())

    def test_kakao_still_connects_verified_member(self):
        make_member(email="minju@kakao.com", nickname="민주")
        res = come_back_from_provider(self.client, kakao_login())
        self.assertEqual(res["Location"], "/write")
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["nickname"], "민주")


class PostViewCountTests(APITestCase):
    def setUp(self):
        owner = make_member()
        blog = Blog.objects.create(owner=owner, address="minju", name="민주의 한채")
        self.post = Post.objects.create(
            blog=blog, post_no=1, content="x", content_text="x", status="PUBLISHED", published_at=timezone.now()
        )
        self.url = "/api/blogs/minju/posts/1/views"

    def views(self):
        self.post.refresh_from_db()
        return self.post.view_count

    def test_cookieless_repeats_from_one_ip_count_once(self):
        for _ in range(5):
            APIClient().post(self.url)  # 매번 쿠키 없이 (새 방문자인 척)
        self.assertEqual(self.views(), 1)
        # 다른 IP 의 새 방문자는 센다
        APIClient().post(self.url, HTTP_X_FORWARDED_FOR="10.0.0.9")
        self.assertEqual(self.views(), 2)

    def test_visitor_with_cookie_counts_once_per_window(self):
        client = APIClient()
        client.post(self.url)
        client.post(self.url)
        self.assertEqual(self.views(), 1)

    def test_needs_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url).status_code, 403)
        client.get("/api/auth/csrf")
        res = client.post(self.url, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.views(), 1)


# 운영 화면은 정적 파일 목록(collectstatic)을 쓰는데 테스트에서는 만들지 않는다
@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class AdminLoginLockTests(APITestCase):
    def setUp(self):
        User.objects.create_superuser("admin@example.com", "admin-pass-1234", nickname="관리")
        self.client = APIClient()

    def login(self, password, ip="10.0.0.1"):
        return self.client.post(
            "/django-admin/login/?next=/django-admin/",
            {"username": "admin@example.com", "password": password},
            HTTP_X_FORWARDED_FOR=ip,
        )

    def test_repeated_wrong_passwords_lock_the_account(self):
        for i in range(10):
            self.assertEqual(self.login("wrong", ip=f"10.0.1.{i}").status_code, 200)
        # 여러 IP 에서 틀려도 계정이 잠긴다. 맞는 비밀번호도 받지 않는다
        self.assertEqual(self.login("admin-pass-1234", ip="10.0.2.1").status_code, 429)

    def test_one_ip_is_locked_for_any_account(self):
        for _ in range(10):
            self.client.post("/django-admin/login/", {"username": "x@example.com", "password": "no"}, HTTP_X_FORWARDED_FOR="10.0.3.1")
        res = self.client.post(
            "/django-admin/login/", {"username": "admin@example.com", "password": "admin-pass-1234"}, HTTP_X_FORWARDED_FOR="10.0.3.1"
        )
        self.assertEqual(res.status_code, 429)

    def test_right_password_logs_in(self):
        self.assertEqual(self.login("admin-pass-1234").status_code, 302)
