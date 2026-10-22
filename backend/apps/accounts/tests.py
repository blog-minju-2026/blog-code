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


def mail_key(index=-1):
    """보낸 인증 메일의 링크(/verify-email?key=...)에 담긴 키."""
    return re.search(r"/verify-email\?key=([^\s]+)", mail.outbox[index].body).group(1)


def verify(client, key, password=SIGNUP["password"]):
    return client.post("/api/auth/email/verify", {"key": key, "password": password}, format="json")


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

        # 메일의 링크는 프론트의 인증 화면으로 간다. 가입할 때 정한 비밀번호를 넣으면 인증하고 바로 로그인된다
        res = verify(self.client, mail_key())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["user"]["nickname"], "민주")
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["email"], SIGNUP["email"])

        self.client.post("/api/auth/logout")
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
        res = verify(self.client, "nope")
        self.assertEqual(res.status_code, 400)
        self.assertIn("key", res.json()["error"]["fields"])

    def test_common_or_similar_password_is_rejected(self):
        for password, message in [
            ("password123", "흔한"),
            ("84729163052", "숫자로만"),
            ("minju@example.com", "비슷한"),
        ]:
            res = self.client.post("/api/auth/signup", {**SIGNUP, "password": password}, format="json")
            self.assertEqual(res.status_code, 400, password)
            self.assertIn(message, res.json()["error"]["fields"]["password"])

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

    def test_login_ends_when_browser_closes(self):
        # 세션 쿠키에 만료일이 없어야 브라우저를 닫을 때 지워진다. 서버 쪽 세션은 2주
        cookie = self.login().cookies["sessionid"]
        self.assertEqual((cookie["expires"], cookie["max-age"]), ("", ""))
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), 60 * 60 * 24 * 14)

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
        res = verify(self.client, mail_key(0))
        self.assertEqual(res.status_code, 400)
        self.assertIn("key", res.json()["error"]["fields"])

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
        self.assertEqual(verify(self.client, mail_key()).status_code, 200)
        self.client.post("/api/auth/logout")
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


class VerifyNeedsPasswordTests(APITestCase):
    """인증 링크만으로는 인증되지 않는다. 남의 이메일로 먼저 가입해 둔 사람의 비밀번호로 계정이 열리지 않게."""

    def setUp(self):
        self.client.post("/api/auth/signup", SIGNUP, format="json")

    def test_wrong_password_does_not_verify(self):
        res = verify(self.client, mail_key(), "not-my-password")
        self.assertEqual(res.status_code, 400)
        self.assertIn("password", res.json()["error"]["fields"])
        self.assertFalse(EmailAddress.objects.get(email=SIGNUP["email"]).verified)
        self.assertEqual(self.client.get("/api/auth/me").json(), {"user": None})

    def test_used_link_cannot_be_used_again(self):
        self.assertEqual(verify(self.client, mail_key()).status_code, 200)
        self.assertIn("key", verify(APIClient(), mail_key()).json()["error"]["fields"])

    def test_suspended_signup_is_verified_but_not_logged_in(self):
        admin = make_member("admin@example.com", "관리인")
        UserSanction.objects.create(
            user=User.objects.get(email=SIGNUP["email"]), admin=admin, reason="스팸",
            starts_at=timezone.now() - timedelta(hours=1), ends_at=None,
        )
        res = verify(self.client, mail_key())
        self.assertEqual(res.json(), {"verified": True, "user": None})
        self.assertTrue(EmailAddress.objects.get(email=SIGNUP["email"]).verified)
        self.assertEqual(self.client.get("/api/auth/me").json(), {"user": None})

    def test_mail_owner_takes_back_signup_made_by_someone_else(self):
        """다른 사람이 내 이메일로 가입해 두었다: 링크를 열어도 그 사람의 비밀번호를 몰라 인증할 수 없다.
        비밀번호 재설정으로 내 비밀번호를 정하면 인증도 마치고, 먼저 가입한 사람의 비밀번호는 더는 맞지 않는다."""
        self.assertEqual(verify(self.client, mail_key(), "what-is-it").status_code, 400)

        self.client.post("/api/auth/password/reset", {"email": SIGNUP["email"]}, format="json")
        uid, token = reset_link()
        res = self.client.post("/api/auth/password/reset/confirm", {"uid": uid, "token": token, "password": "mine-5678!"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(EmailAddress.objects.get(email=SIGNUP["email"]).verified)

        login = lambda password: self.client.post("/api/auth/login", {"email": SIGNUP["email"], "password": password}, format="json")
        self.assertEqual(login(SIGNUP["password"]).status_code, 401)
        self.assertEqual(login("mine-5678!").status_code, 200)


def reset_link(index=-1):
    """보낸 비밀번호 재설정 메일의 링크(/reset-password?uid=..&token=..)에 담긴 uid · token."""
    found = re.search(r"/reset-password\?uid=([^&\s]+)&token=([^\s]+)", mail.outbox[index].body)
    return found.group(1), found.group(2)


class PasswordResetTests(APITestCase):
    url = "/api/auth/password/reset"

    def setUp(self):
        self.user = make_member()

    def confirm(self, password="new-pass-5678", **link):
        uid, token = reset_link()
        body = {"uid": uid, "token": token, "password": password, **link}
        return self.client.post(f"{self.url}/confirm", body, format="json")

    def test_reset_then_login_with_new_password(self):
        res = self.client.post(self.url, {"email": "MINJU@example.com"}, format="json")
        self.assertEqual((res.status_code, res.json()), (200, {"sent": True}))
        self.assertEqual(mail.outbox[0].subject, "[한채] 비밀번호를 새로 정해 주세요")
        self.assertEqual(self.confirm().json(), {"reset": True})

        login = lambda password: self.client.post("/api/auth/login", {"email": "minju@example.com", "password": password}, format="json")
        self.assertEqual(login("hanchae-1234").status_code, 401)
        self.assertEqual(login("new-pass-5678").status_code, 200)

    def test_link_works_only_once(self):
        self.client.post(self.url, {"email": "minju@example.com"}, format="json")
        self.assertEqual(self.confirm().status_code, 200)
        res = self.confirm("another-pass-90")
        self.assertEqual(res.status_code, 400)
        self.assertIn("token", res.json()["error"]["fields"])

    def test_bad_link_and_weak_password(self):
        self.client.post(self.url, {"email": "minju@example.com"}, format="json")
        self.assertIn("token", self.confirm(token="nope").json()["error"]["fields"])
        self.assertIn("token", self.confirm(uid="!!").json()["error"]["fields"])
        res = self.confirm("password123")
        self.assertEqual(res.status_code, 400)
        self.assertIn("흔한", res.json()["error"]["fields"]["password"])
        self.assertTrue(self.client.login(email="minju@example.com", password="hanchae-1234"))  # 그대로다

    def test_unknown_email_gets_same_answer_without_mail(self):
        res = self.client.post(self.url, {"email": "nobody@example.com"}, format="json")
        self.assertEqual((res.status_code, res.json()), (200, {"sent": True}))
        self.assertEqual(len(mail.outbox), 0)

    def test_once_a_minute(self):
        self.client.post(self.url, {"email": "minju@example.com"}, format="json")
        res = self.client.post(self.url, {"email": "minju@example.com"}, format="json")
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"]["code"], "TOO_MANY_REQUESTS")
        self.assertEqual(len(mail.outbox), 1)

    def test_reset_logs_out_other_sessions(self):
        other = APIClient()
        other.login(email="minju@example.com", password="hanchae-1234")
        self.client.post(self.url, {"email": "minju@example.com"}, format="json")
        self.confirm()
        self.assertEqual(other.get("/api/auth/me").json(), {"user": None})

    def test_mail_failure_is_503_and_can_retry_right_away(self):
        from django.test import override_settings

        with override_settings(EMAIL_BACKEND="apps.accounts.tests.FailingMailBackend"):
            res = self.client.post(self.url, {"email": "minju@example.com"}, format="json")
        self.assertEqual((res.status_code, res.json()["error"]["code"]), (503, "MAIL_FAILED"))
        self.assertEqual(self.client.post(self.url, {"email": "minju@example.com"}, format="json").status_code, 200)


class LoginLockTests(APITestCase):
    """비밀번호를 거듭 틀리면 그 이메일로는 잠시 로그인을 막는다."""

    def setUp(self):
        make_member()

    def login(self, password, client=None):
        client = client or APIClient()  # IP 마다의 제한과 상관없이 이메일마다 센다
        return client.post("/api/auth/login", {"email": "minju@example.com", "password": password}, format="json")

    def test_locked_after_ten_failures_even_with_right_password(self):
        from . import attempts

        for _ in range(attempts.FAILURE_LIMIT):
            self.assertEqual(self.login("wrong-password").status_code, 401)
        res = self.login("hanchae-1234")
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"]["code"], "TOO_MANY_REQUESTS")
        self.assertIn("15분", res.json()["error"]["message"])

        attempts.clear("minju@example.com")  # 기한이 지난 것처럼
        self.assertEqual(self.login("hanchae-1234").status_code, 200)

    def test_success_resets_the_count(self):
        from . import attempts

        for _ in range(attempts.FAILURE_LIMIT - 1):
            self.login("wrong-password")
        self.assertEqual(self.login("hanchae-1234").status_code, 200)
        for _ in range(attempts.FAILURE_LIMIT - 1):
            self.login("wrong-password")
        self.assertEqual(self.login("hanchae-1234").status_code, 200)


class ThrottleTests(APITestCase):
    def test_login_is_limited_per_ip(self):
        for _ in range(30):
            self.client.post("/api/auth/login", {"email": "x@example.com", "password": "nope-nope"}, format="json")
        res = self.client.post("/api/auth/login", {"email": "y@example.com", "password": "nope-nope"}, format="json")
        self.assertEqual(res.status_code, 429)
        error = res.json()["error"]
        self.assertEqual(error["code"], "TOO_MANY_REQUESTS")
        self.assertIn("뒤에 다시 시도해 주세요", error["message"])
        self.assertGreater(error["detail"]["retry_after"], 0)
        self.assertIn("Retry-After", res.headers)

        # IP 는 nginx 가 X-Forwarded-For 끝에 붙인 값으로 센다. 앞쪽에 아무 값이나 적어 보내도 같은 IP 다
        spoofed = self.client.post(
            "/api/auth/login", {"email": "y@example.com", "password": "nope-nope"}, format="json",
            HTTP_X_FORWARDED_FOR="1.2.3.4, 127.0.0.1",
        )
        self.assertEqual(spoofed.status_code, 429)
        other = self.client.post(
            "/api/auth/login", {"email": "y@example.com", "password": "nope-nope"}, format="json",
            HTTP_X_FORWARDED_FOR="10.0.0.9",
        )
        self.assertEqual(other.status_code, 401)
