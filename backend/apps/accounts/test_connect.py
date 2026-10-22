"""소셜 계정 연동 (AUTH-07): 로그인한 회원이 제공사 계정을 잇고 끊는다."""

from allauth.core import context
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import get_user
from django.test import RequestFactory
from rest_framework.test import APITestCase

from .models import User
from .test_social import AGREE, come_back_from_provider, google_login, kakao_login, social_settings
from .tests import make_member

PASSWORD = "hanchae-1234"


def connect_back(client, answer):
    """로그인한 채로 제공사에서 돌아온 순간(callback, process=connect)."""
    request = RequestFactory().get("/accounts/kakao/login/callback/")
    request.session = client.session
    request.user = get_user(request)
    with context.request_context(request):
        provider = get_social_adapter().get_provider(request, answer["provider"])
        sociallogin = provider.sociallogin_from_response(request, answer["data"])
        sociallogin.state = {"process": "connect", "next": "/somewhere"}
        response = complete_social_login(request, sociallogin)
    request.session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = request.session.session_key
    return response


@social_settings
class ConnectTests(APITestCase):
    def setUp(self):
        self.minju = make_member()  # 이메일 minju@example.com · 비밀번호 있음
        self.client.force_login(self.minju)

    def start(self, provider="kakao", **body):
        return self.client.post("/api/me/social/connect", {"provider": provider, **body}, format="json")

    def test_login_methods_lists_enabled_providers(self):
        data = self.client.get("/api/me/login-methods").json()
        self.assertEqual(data["email"], "minju@example.com")
        self.assertTrue(data["has_password"])
        self.assertEqual(data["confirm_with"], "password")
        self.assertEqual([p["provider"] for p in data["providers"]], ["kakao", "google"])
        self.assertFalse(any(p["connected"] for p in data["providers"]))

    def test_connect_with_different_email_then_log_in_either_way(self):
        self.assertEqual(self.start(password="wrong-pass").json()["error"]["fields"], {"password": "비밀번호가 맞지 않아요."})
        self.assertEqual(self.start(password=PASSWORD).status_code, 200)

        res = connect_back(self.client, kakao_login(email="totally-other@kakao.com"))
        self.assertEqual(res["Location"], "/me?connect=done&provider=kakao")
        account = SocialAccount.objects.get()
        self.assertEqual(account.user, self.minju)
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["nickname"], "민주")  # 그대로 로그인
        kakao = self.client.get("/api/me/login-methods").json()["providers"][0]
        self.assertTrue(kakao["connected"])
        self.assertTrue(kakao["can_disconnect"])  # 비밀번호가 있다

        # 이제 카카오로도, 이메일로도 같은 한채로 들어온다
        self.client.post("/api/auth/logout")
        res = come_back_from_provider(self.client, kakao_login(email="totally-other@kakao.com"))
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["nickname"], "민주")
        self.client.post("/api/auth/logout")
        login = self.client.post("/api/auth/login", {"email": "minju@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(login.status_code, 200)

    def test_connect_needs_identity_check_first_and_only_once(self):
        res = connect_back(self.client, kakao_login())
        self.assertEqual(res["Location"], "/me?connect=error&provider=kakao")
        self.start(password=PASSWORD)
        connect_back(self.client, kakao_login())
        SocialAccount.objects.all().delete()
        res = connect_back(self.client, kakao_login(uid="2002"))  # 확인 표시는 한 번만 쓴다
        self.assertEqual(res["Location"], "/me?connect=error&provider=kakao")
        self.assertFalse(SocialAccount.objects.exists())

    def test_allowance_is_for_that_provider_only(self):
        self.start(provider="google", password=PASSWORD)
        res = connect_back(self.client, kakao_login())
        self.assertEqual(res["Location"], "/me?connect=error&provider=kakao")

    def test_account_of_another_member_is_refused(self):
        other = make_member(email="seohyun@example.com", nickname="서현")
        SocialAccount.objects.create(user=other, provider="kakao", uid="1001")
        self.start(password=PASSWORD)
        res = connect_back(self.client, kakao_login(uid="1001"))
        self.assertEqual(res["Location"], "/me?connect=taken&provider=kakao")
        self.assertEqual(SocialAccount.objects.get().user, other)

    def test_email_of_another_member_does_not_block_connect(self):
        # 카카오 이메일이 다른 회원의 인증된 이메일과 같아도, 이어지지 않은 카카오 계정이면 나에게 잇는다
        make_member(email="seohyun@kakao.com", nickname="서현")
        self.start(password=PASSWORD)
        res = connect_back(self.client, kakao_login(email="seohyun@kakao.com"))
        self.assertEqual(res["Location"], "/me?connect=done&provider=kakao")
        self.assertEqual(SocialAccount.objects.get().user, self.minju)

    def test_one_account_per_provider(self):
        SocialAccount.objects.create(user=self.minju, provider="kakao", uid="1001")
        self.assertEqual(self.start(password=PASSWORD).status_code, 409)
        self.assertEqual(self.start(provider="naver", password=PASSWORD).status_code, 400)  # 켜지지 않은 제공사

    def test_disconnect(self):
        SocialAccount.objects.create(user=self.minju, provider="kakao", uid="1001")
        res = self.client.delete("/api/me/social/kakao")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(SocialAccount.objects.exists())
        self.assertEqual(self.client.delete("/api/me/social/kakao").status_code, 404)


@social_settings
class SocialOnlyMemberTests(APITestCase):
    """비밀번호 없이 카카오로만 가입한 회원."""

    def setUp(self):
        come_back_from_provider(self.client, kakao_login())
        self.client.post("/api/auth/social/signup", {"nickname": "민주", **AGREE}, format="json")
        self.user = User.objects.get()

    def test_last_login_method_cannot_be_cut(self):
        kakao = self.client.get("/api/me/login-methods").json()["providers"][0]
        self.assertFalse(kakao["can_disconnect"])
        res = self.client.delete("/api/me/social/kakao")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "LAST_LOGIN_METHOD")
        self.assertTrue(SocialAccount.objects.filter(user=self.user).exists())

    def test_confirms_with_nickname_and_then_can_cut_one_of_two(self):
        self.assertEqual(self.client.get("/api/me/login-methods").json()["confirm_with"], "nickname")
        self.assertEqual(self.client.post("/api/me/social/connect", {"provider": "google", "nickname": "민지"}, format="json").status_code, 400)
        self.client.post("/api/me/social/connect", {"provider": "google", "nickname": "민주"}, format="json")
        res = connect_back(self.client, google_login(uid="g-9", email="minju-google@example.com"))
        self.assertEqual(res["Location"], "/me?connect=done&provider=google")

        methods = {p["provider"]: p for p in self.client.get("/api/me/login-methods").json()["providers"]}
        self.assertTrue(methods["kakao"]["can_disconnect"] and methods["google"]["can_disconnect"])
        self.assertEqual(self.client.delete("/api/me/social/kakao").status_code, 200)
        self.assertEqual(self.client.delete("/api/me/social/google").status_code, 409)  # 이제 마지막 하나
