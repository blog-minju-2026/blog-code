"""소셜 로그인 (AUTH-03).

제공사와 주고받는 부분(인가 화면 · 토큰)은 allauth 가 맡으므로, 테스트는 제공사에서 돌아온 순간부터 본다.
come_back_from_provider 가 callback 이 하는 일(받은 계정으로 로그인 · 가입 흐름 타기)을 테스트 클라이언트의 세션으로 흉내 낸다.
"""

from allauth.account.models import EmailAddress
from allauth.core import context
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from allauth.socialaccount.helpers import complete_social_login, render_authentication_error
from allauth.socialaccount.models import SocialAccount, SocialLogin
from allauth.socialaccount.providers.base import AuthError
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, override_settings
from django.urls import include, path
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.moderation.models import UserSanction
from config import urls as site_urls
from config.urls import social_login_patterns

from .models import User
from .tests import make_member

PROVIDERS = ["kakao", "google"]

# 카카오 · 구글만 켠 사이트
urlpatterns = [path("accounts/", include(social_login_patterns(PROVIDERS)))] + site_urls.urlpatterns

social_settings = override_settings(
    ROOT_URLCONF=__name__,
    SOCIAL_PROVIDERS=PROVIDERS,
    SOCIALACCOUNT_PROVIDERS={p: {"APPS": [{"client_id": f"{p}-id", "secret": f"{p}-secret"}]} for p in PROVIDERS},
)

AGREE = {"agree_terms": True, "agree_privacy": True, "over_14": True}


def kakao_login(uid="1001", email="minju@kakao.com", verified=True, nickname="카카오민주", next_url="/write"):
    """카카오가 돌려준 사용자 정보 (GET /v2/user/me)."""
    account = {"profile": {"nickname": nickname}}
    if email:
        account.update(email=email, is_email_verified=verified)
    return {"provider": "kakao", "data": {"id": int(uid), "kakao_account": account}, "next": next_url}


def google_login(uid="g-1", email="minju@example.com", next_url="/"):
    data = {"sub": uid, "email": email, "email_verified": True, "name": "Minju Chae"}
    return {"provider": "google", "data": data, "next": next_url}


def provider_request(client):
    request = RequestFactory().get("/accounts/kakao/login/callback/")
    request.session = client.session
    request.user = AnonymousUser()
    return request


def come_back_from_provider(client, answer, process="login"):
    """제공사에서 돌아온 순간(callback): 제공사가 준 사용자 정보로 allauth 의 로그인 · 가입 흐름을 탄다."""
    request = provider_request(client)
    with context.request_context(request):
        provider = get_social_adapter().get_provider(request, answer["provider"])
        sociallogin = provider.sociallogin_from_response(request, answer["data"])
        sociallogin.state = {"process": process, "next": answer["next"]}
        response = complete_social_login(request, sociallogin)
    request.session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = request.session.session_key
    return response


@social_settings
class SocialSignupTests(APITestCase):
    def test_first_visit_finishes_signup_with_nickname_and_agreements(self):
        res = come_back_from_provider(self.client, kakao_login())
        self.assertEqual(res["Location"], "/accounts/social/signup/")
        self.assertEqual(self.client.get(res["Location"])["Location"], "/login?social=signup")
        self.assertFalse(User.objects.exists())

        status = self.client.get("/api/auth/social").json()
        self.assertEqual(status["providers"], PROVIDERS)
        self.assertEqual(
            status["signup"],
            {"provider": "kakao", "provider_name": "카카오", "email": "minju@kakao.com", "nickname": "카카오민주"},
        )

        res = self.client.post("/api/auth/social/signup", {"nickname": "민주", **AGREE}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["next"], "/write")
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["nickname"], "민주")

        user = User.objects.get()
        self.assertEqual(user.email, "minju@kakao.com")
        self.assertFalse(user.has_usable_password())
        self.assertIsNotNone(user.terms_agreed_at)
        self.assertTrue(EmailAddress.objects.get(user=user).verified)
        self.assertEqual(SocialAccount.objects.get(user=user).uid, "1001")
        self.assertIsNone(self.client.get("/api/auth/social").json()["signup"])

    def test_agreements_are_required(self):
        come_back_from_provider(self.client, kakao_login())
        res = self.client.post("/api/auth/social/signup", {"nickname": "민주", **AGREE, "over_14": False}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("over_14", res.json()["error"]["fields"])
        self.assertFalse(User.objects.exists())

    def test_signup_without_pending_social_login(self):
        res = self.client.post("/api/auth/social/signup", {"nickname": "민주", **AGREE}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "SOCIAL_SIGNUP_EXPIRED")

    def test_nickname_taken(self):
        make_member(email="other@example.com", nickname="민주")
        come_back_from_provider(self.client, kakao_login())
        res = self.client.post("/api/auth/social/signup", {"nickname": "민주", **AGREE}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertIn("nickname", res.json()["error"]["fields"])

    def test_unverified_or_missing_email_is_not_kept(self):
        come_back_from_provider(self.client, kakao_login(verified=False))
        self.assertIsNone(self.client.get("/api/auth/social").json()["signup"]["email"])
        self.client.post("/api/auth/social/signup", {"nickname": "민주", **AGREE}, format="json")
        user = User.objects.get()
        self.assertIsNone(user.email)
        self.assertFalse(EmailAddress.objects.exists())

        # 카카오 일반 앱처럼 이메일을 아예 주지 않아도 가입된다
        self.client.post("/api/auth/logout")
        come_back_from_provider(self.client, kakao_login(uid="1002", email=None))
        res = self.client.post("/api/auth/social/signup", {"nickname": "두번째", **AGREE}, format="json")
        self.assertEqual(res.status_code, 201)

    def test_existing_social_member_logs_in_directly(self):
        come_back_from_provider(self.client, kakao_login())
        self.client.post("/api/auth/social/signup", {"nickname": "민주", **AGREE}, format="json")
        self.client.post("/api/auth/logout")

        res = come_back_from_provider(self.client, kakao_login(next_url="/me"))
        self.assertEqual(res["Location"], "/me")
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["nickname"], "민주")
        self.assertEqual(User.objects.count(), 1)


@social_settings
class ProviderProfileTests(APITestCase):
    """제공사의 프로필 원본(extra_data)은 남기지 않는다. 세션에도 닉네임 칸에 채울 별명만."""

    def test_pending_signup_keeps_only_nickname_in_session(self):
        come_back_from_provider(self.client, kakao_login())
        pending = SocialLogin.deserialize(self.client.session["socialaccount_sociallogin"])
        self.assertEqual(pending.account.extra_data, {"nickname": "카카오민주"})

    def test_saved_account_has_no_profile_even_after_login_again(self):
        come_back_from_provider(self.client, kakao_login())
        self.client.post("/api/auth/social/signup", {"nickname": "민주", **AGREE}, format="json")
        self.assertEqual(SocialAccount.objects.get().extra_data, {})

        self.client.post("/api/auth/logout")
        come_back_from_provider(self.client, kakao_login(nickname="바뀐별명"))
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["nickname"], "민주")
        self.assertEqual(SocialAccount.objects.get().extra_data, {})

    def test_connected_account_has_no_profile(self):
        make_member(email="minju@example.com", nickname="민주")
        come_back_from_provider(self.client, google_login())
        self.assertEqual(SocialAccount.objects.get().extra_data, {})


@social_settings
class SocialEmailConnectTests(APITestCase):
    def test_verified_member_with_same_email_is_connected(self):
        member = make_member(email="minju@example.com", nickname="민주")
        res = come_back_from_provider(self.client, google_login(email="MINJU@example.com"))
        self.assertEqual(res["Location"], "/")
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["nickname"], "민주")
        self.assertEqual(SocialAccount.objects.get().user, member)
        member.refresh_from_db()
        self.assertTrue(member.has_usable_password())  # 이메일 로그인도 그대로

    def test_pending_signup_with_same_email_is_not_connected_and_gives_way(self):
        # 남이 내 이메일로 먼저 가입만 해 두고 인증하지 않은 경우
        squatter = make_member(email="minju@example.com", nickname="먼저온이", verified=False)
        res = come_back_from_provider(self.client, google_login())
        self.assertEqual(res["Location"], "/accounts/social/signup/")

        res = self.client.post("/api/auth/social/signup", {"nickname": "민주", **AGREE}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertFalse(User.objects.filter(pk=squatter.pk).exists())
        self.assertEqual(User.objects.get().email, "minju@example.com")


@social_settings
class SocialLoginBlockedTests(APITestCase):
    def setUp(self):
        come_back_from_provider(self.client, kakao_login())
        self.client.post("/api/auth/social/signup", {"nickname": "민주", **AGREE}, format="json")
        self.client.post("/api/auth/logout")
        self.user = User.objects.get()

    def test_suspended_member_is_turned_back_with_reason(self):
        admin = make_member(email="admin@example.com", nickname="관리인")
        UserSanction.objects.create(user=self.user, admin=admin, reason="도배", starts_at=timezone.now())

        res = come_back_from_provider(self.client, kakao_login())
        self.assertEqual(res["Location"], "/login?social=suspended")
        self.assertIsNone(self.client.get("/api/auth/me").json()["user"])
        # 사유는 한 번만 알린다
        self.assertEqual(self.client.get("/api/auth/social").json()["blocked"], {"reason": "도배", "ends_at": None})
        self.assertIsNone(self.client.get("/api/auth/social").json()["blocked"])

    def test_withdrawn_member_is_turned_back(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        res = come_back_from_provider(self.client, kakao_login())
        self.assertEqual(res["Location"], "/login?social=inactive")
        self.assertIsNone(self.client.get("/api/auth/me").json()["user"])

    def test_connect_process_is_closed(self):
        res = come_back_from_provider(self.client, kakao_login(), process="connect")
        self.assertEqual(res["Location"], "/login?social=error")


@social_settings
class SocialLoginPagesTests(APITestCase):
    def test_provider_errors_go_back_to_login(self):
        request = provider_request(self.client)
        with context.request_context(request):
            provider = get_social_adapter().get_provider(request, "kakao")
            self.assertEqual(
                render_authentication_error(request, provider, error=AuthError.CANCELLED)["Location"],
                "/login?social=cancelled",
            )
            self.assertEqual(render_authentication_error(request, provider)["Location"], "/login?social=error")

    def test_login_button_posts_to_provider(self):
        res = self.client.post("/accounts/kakao/login/", {"process": "login", "next": "/write"})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res["Location"].startswith("https://kauth.kakao.com/oauth/authorize"))
        self.assertIn("kakao-id", res["Location"])
        # 주소를 직접 열면 로그인 화면으로
        self.assertIn('url=/login', self.client.get("/accounts/kakao/login/").content.decode())

    def test_only_enabled_provider_login_is_open(self):
        for url in ("/accounts/login/", "/accounts/signup/", "/accounts/password/reset/", "/accounts/3rdparty/",
                    "/accounts/naver/login/"):
            self.assertEqual(self.client.get(url).status_code, 404, url)


@social_settings
class FrontendRequestTests(APITestCase):
    """화면(js/auth.js)이 보내는 그대로: CSRF 검사를 켠 채 부른다."""

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.get("/api/auth/csrf")
        self.token = self.client.cookies["csrftoken"].value

    def test_provider_button_form_needs_csrf_token(self):
        # startSocialLogin 의 폼: csrfmiddlewaretoken · process · next
        form = {"process": "login", "next": "/write"}
        self.assertEqual(self.client.post("/accounts/kakao/login/", form).status_code, 403)
        res = self.client.post("/accounts/kakao/login/", {**form, "csrfmiddlewaretoken": self.token})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res["Location"].startswith("https://kauth.kakao.com/"))

    def test_finish_signup_with_csrf_header(self):
        come_back_from_provider(self.client, kakao_login())
        body = {"nickname": "민주", **AGREE}  # finishSocialSignup 이 보내는 칸
        self.assertEqual(self.client.post("/api/auth/social/signup", body, format="json").status_code, 403)

        status = self.client.get("/api/auth/social").json()
        self.assertEqual(set(status), {"providers", "signup", "blocked"})
        self.assertEqual(set(status["signup"]), {"provider", "provider_name", "email", "nickname"})
        self.assertEqual(self.client.get("/api/auth/nickname-available", {"nickname": "민주"}).json(),
                         {"available": True, "reason": None})

        res = self.client.post("/api/auth/social/signup", body, format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(set(res.json()), {"user", "next"})
