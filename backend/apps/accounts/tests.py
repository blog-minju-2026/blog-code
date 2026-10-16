import re
from datetime import timedelta

from allauth.account.models import EmailAddress
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.moderation.models import UserSanction

from .models import User

SIGNUP = {
    "email": "minju@example.com",
    "password": "hanchae-1234",
    "nickname": "민주",
    "agree_terms": True,
    "agree_privacy": True,
    "over_14": True,
}


def make_member(email="minju@example.com", nickname="민주", password="hanchae-1234", verified=True):
    user = User.objects.create_user(email, password, nickname=nickname)
    EmailAddress.objects.create(user=user, email=email, primary=True, verified=verified)
    return user


class SignupFlowTests(APITestCase):
    def test_signup_sends_mail_then_verify_then_login(self):
        res = self.client.post("/api/auth/signup", SIGNUP, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json(), {"email_verification_sent": True})
        self.assertEqual(len(mail.outbox), 1)

        login = {"email": SIGNUP["email"], "password": SIGNUP["password"]}
        self.assertEqual(self.client.post("/api/auth/login", login, format="json").json()["error"]["code"], "EMAIL_NOT_VERIFIED")

        # 메일의 링크는 프론트의 인증 화면으로 간다
        key = re.search(r"/verify-email\?key=([^\s]+)", mail.outbox[0].body).group(1)
        self.assertEqual(self.client.post("/api/auth/email/verify", {"key": key}, format="json").status_code, 200)

        res = self.client.post("/api/auth/login", login, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["user"]["nickname"], "민주")
        self.assertIsNone(res.json()["user"]["blog_address"])

    def test_duplicate_email_and_nickname_conflict(self):
        make_member()
        res = self.client.post("/api/auth/signup", SIGNUP, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(set(res.json()["error"]["fields"]), {"email", "nickname"})

    def test_email_is_case_insensitive(self):
        make_member()
        res = self.client.post("/api/auth/signup", {**SIGNUP, "email": "MINJU@example.com", "nickname": "다른이"}, format="json")
        self.assertEqual(res.status_code, 409)

    def test_signup_rules(self):
        bad = {**SIGNUP, "password": "short", "nickname": "a", "agree_terms": False, "over_14": False}
        res = self.client.post("/api/auth/signup", bad, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(set(res.json()["error"]["fields"]), {"password", "nickname", "agree_terms", "over_14"})

    def test_bad_verify_key(self):
        res = self.client.post("/api/auth/email/verify", {"key": "nope"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_signup_requires_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        res = client.post("/api/auth/signup", SIGNUP, format="json")
        self.assertEqual(res.status_code, 403)

        client.get("/api/auth/csrf")
        token = client.cookies["csrftoken"].value
        res = client.post("/api/auth/signup", SIGNUP, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, 201)


class LoginTests(APITestCase):
    def setUp(self):
        self.user = make_member()

    def login(self, password="hanchae-1234"):
        return self.client.post("/api/auth/login", {"email": "minju@example.com", "password": password}, format="json")

    def test_me_is_null_for_visitors(self):
        self.assertEqual(self.client.get("/api/auth/me").json(), {"user": None})

    def test_wrong_password(self):
        res = self.login("wrong-password")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"]["code"], "LOGIN_FAILED")

    def test_login_me_logout(self):
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["email"], "minju@example.com")
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me").json(), {"user": None})

    def test_logout_needs_login(self):
        res = self.client.post("/api/auth/logout")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"]["code"], "AUTH_REQUIRED")

    def test_suspended_member_cannot_login(self):
        admin = make_member("admin@example.com", "관리인")
        UserSanction.objects.create(
            user=self.user, admin=admin, reason="스팸 댓글", starts_at=timezone.now() - timedelta(hours=1),
            ends_at=timezone.now() + timedelta(days=3),
        )
        res = self.login()
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"]["code"], "SUSPENDED")
        self.assertEqual(res.json()["error"]["detail"]["reason"], "스팸 댓글")

    def test_expired_sanction_allows_login(self):
        admin = make_member("admin@example.com", "관리인")
        UserSanction.objects.create(
            user=self.user, admin=admin, reason="지난 제한", starts_at=timezone.now() - timedelta(days=5),
            ends_at=timezone.now() - timedelta(days=1),
        )
        self.assertEqual(self.login().status_code, 200)


class NicknameAndMeTests(APITestCase):
    def setUp(self):
        self.user = make_member()
        make_member("seohyun@example.com", "서현")

    def test_nickname_available(self):
        get = lambda n: self.client.get("/api/auth/nickname-available", {"nickname": n}).json()
        self.assertEqual(get("서현"), {"available": False, "reason": "TAKEN"})
        self.assertEqual(get("가"), {"available": False, "reason": "INVALID"})
        self.assertEqual(get("새이름"), {"available": True, "reason": None})

    def test_update_nickname(self):
        self.client.force_authenticate(self.user)
        res = self.client.patch("/api/me", {"nickname": "민주2"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["user"]["nickname"], "민주2")
        res = self.client.patch("/api/me", {"nickname": "서현"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("nickname", res.json()["error"]["fields"])


class FailingMailBackend:
    """SMTP 서버에 닿지 못한 것처럼 실패하는 메일 백엔드 (테스트용)."""

    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, messages):
        import smtplib

        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")


class SignupMailTests(APITestCase):
    def test_mail_subject_and_sender(self):
        self.client.post("/api/auth/signup", SIGNUP, format="json")
        self.assertEqual(mail.outbox[0].subject, "[한채] 이메일 인증을 마쳐 주세요")
        self.assertTrue(mail.outbox[0].from_email.startswith("한채 <"))

    def test_signup_is_rolled_back_when_mail_fails(self):
        """메일을 못 보내면 가입도 되돌려, 다시 가입할 수 있게 한다."""
        from django.test import override_settings

        with override_settings(EMAIL_BACKEND="apps.accounts.tests.FailingMailBackend"):
            res = self.client.post("/api/auth/signup", SIGNUP, format="json")
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["error"]["code"], "MAIL_FAILED")
        self.assertFalse(User.objects.filter(email=SIGNUP["email"]).exists())
        self.assertEqual(self.client.post("/api/auth/signup", SIGNUP, format="json").status_code, 201)


class PendingSignupTests(APITestCase):
    """이메일 인증을 안 마친 가입은 회원이 아니다. 이메일을 잘못 써 인증할 수 없는 가입이 자리를 붙잡지 않게 한다."""

    def setUp(self):
        self.client.post("/api/auth/signup", {**SIGNUP, "email": "minju@exmaple.com"}, format="json")  # 오타

    def expire(self, email="minju@exmaple.com"):
        User.objects.filter(email=email).update(created_at=timezone.now() - timedelta(days=4))

    def test_nickname_is_released_for_signup_with_another_email(self):
        res = self.client.post("/api/auth/signup", SIGNUP, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertFalse(User.objects.filter(email="minju@exmaple.com").exists())
        self.assertFalse(EmailAddress.objects.filter(email="minju@exmaple.com").exists())
        # 지운 가입의 링크는 더는 쓸 수 없다
        old_key = re.search(r"/verify-email\?key=([^\s]+)", mail.outbox[0].body).group(1)
        self.assertEqual(self.client.post("/api/auth/email/verify", {"key": old_key}, format="json").status_code, 400)

    def test_verified_member_keeps_nickname(self):
        EmailAddress.objects.update(verified=True)
        res = self.client.post("/api/auth/signup", SIGNUP, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(set(res.json()["error"]["fields"]), {"nickname"})

    def test_same_email_waits_until_link_expires(self):
        again = {**SIGNUP, "email": "minju@exmaple.com", "nickname": "다른이"}
        res = self.client.post("/api/auth/signup", again, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertIn("인증 메일을 다시", res.json()["error"]["fields"]["email"])

        self.expire()
        self.assertEqual(self.client.post("/api/auth/signup", again, format="json").status_code, 201)
        self.assertEqual(User.objects.get(email="minju@exmaple.com").nickname, "다른이")

    def test_resent_link_keeps_signup_alive(self):
        self.expire()
        self.client.post("/api/auth/email/resend", {"email": "minju@exmaple.com"}, format="json")
        res = self.client.post("/api/auth/signup", {**SIGNUP, "email": "minju@exmaple.com", "nickname": "다른이"}, format="json")
        self.assertEqual(res.status_code, 409)

    def test_delete_expired_signups_command(self):
        from io import StringIO

        from django.core.management import call_command

        make_member("seohyun@example.com", "서현", verified=False)  # 아직 링크가 살아 있다
        make_member("old@example.com", "옛회원")
        User.objects.filter(email="old@example.com").update(created_at=timezone.now() - timedelta(days=30))  # 인증을 마친 회원은 남는다
        self.expire()

        out = StringIO()
        call_command("delete_expired_signups", "--dry-run", stdout=out)
        self.assertIn("minju@exmaple.com", out.getvalue())
        self.assertTrue(User.objects.filter(email="minju@exmaple.com").exists())

        call_command("delete_expired_signups", stdout=StringIO())
        self.assertEqual(
            set(User.objects.values_list("email", flat=True)), {"seohyun@example.com", "old@example.com"}
        )


class EmailResendTests(APITestCase):
    url = "/api/auth/email/resend"

    def setUp(self):
        self.client.post("/api/auth/signup", SIGNUP, format="json")
        mail.outbox.clear()

    def test_resend_then_verify_with_new_link(self):
        res = self.client.post(self.url, {"email": "MINJU@example.com"}, format="json")  # 대소문자 무시
        self.assertEqual((res.status_code, res.json()), (200, {"sent": True}))
        self.assertEqual(len(mail.outbox), 1)
        key = re.search(r"/verify-email\?key=([^\s]+)", mail.outbox[0].body).group(1)
        self.assertEqual(self.client.post("/api/auth/email/verify", {"key": key}, format="json").status_code, 200)
        login = {"email": SIGNUP["email"], "password": SIGNUP["password"]}
        self.assertEqual(self.client.post("/api/auth/login", login, format="json").status_code, 200)

    def test_once_a_minute(self):
        self.client.post(self.url, {"email": SIGNUP["email"]}, format="json")
        res = self.client.post(self.url, {"email": SIGNUP["email"]}, format="json")
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"]["code"], "TOO_MANY_REQUESTS")
        self.assertEqual(len(mail.outbox), 1)
        # 1분이 지나면 다시 보낼 수 있다
        from .models import VerificationMailLog

        VerificationMailLog.objects.update(last_sent_at=timezone.now() - timedelta(seconds=61))
        self.assertEqual(self.client.post(self.url, {"email": SIGNUP["email"]}, format="json").status_code, 200)
        self.assertEqual(len(mail.outbox), 2)

    def test_unknown_and_verified_get_same_answer_without_mail(self):
        res = self.client.post(self.url, {"email": "nobody@example.com"}, format="json")
        self.assertEqual((res.status_code, res.json()), (200, {"sent": True}))
        EmailAddress.objects.update(verified=True)
        res = self.client.post(self.url, {"email": SIGNUP["email"]}, format="json")
        self.assertEqual((res.status_code, res.json()), (200, {"sent": True}))
        self.assertEqual(len(mail.outbox), 0)

    def test_bad_email_is_400(self):
        self.assertEqual(self.client.post(self.url, {"email": "not-an-email"}, format="json").status_code, 400)

    def test_mail_failure_is_503_and_can_retry_right_away(self):
        from django.test import override_settings

        with override_settings(EMAIL_BACKEND="apps.accounts.tests.FailingMailBackend"):
            res = self.client.post(self.url, {"email": SIGNUP["email"]}, format="json")
        self.assertEqual((res.status_code, res.json()["error"]["code"]), (503, "MAIL_FAILED"))
        self.assertEqual(self.client.post(self.url, {"email": SIGNUP["email"]}, format="json").status_code, 200)
