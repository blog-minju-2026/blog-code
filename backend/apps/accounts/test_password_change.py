"""로그인한 채로 비밀번호 바꾸기 (AUTH-08): POST /api/me/password."""

from django.core.cache import cache
from rest_framework.test import APIClient, APITestCase

from .models import User
from .tests import make_member

OLD = "hanchae-1234"
NEW = "dalbit-maru-5678"


class PasswordChangeTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = make_member()
        self.client.post("/api/auth/login", {"email": "minju@example.com", "password": OLD}, format="json")

    def change(self, current=OLD, new=NEW, client=None):
        return (client or self.client).post("/api/me/password", {"current_password": current, "new_password": new}, format="json")

    def test_change_keeps_this_login_and_cuts_the_others(self):
        other_device = APIClient()
        other_device.post("/api/auth/login", {"email": "minju@example.com", "password": OLD}, format="json")
        self.assertIsNotNone(other_device.get("/api/auth/me").json()["user"])

        res = self.change()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"changed": True})
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["nickname"], "민주")
        self.assertIsNone(other_device.get("/api/auth/me").json()["user"])

        fresh = APIClient()
        self.assertEqual(fresh.post("/api/auth/login", {"email": "minju@example.com", "password": OLD}, format="json").status_code, 401)
        self.assertEqual(fresh.post("/api/auth/login", {"email": "minju@example.com", "password": NEW}, format="json").status_code, 200)

    def test_wrong_current_password(self):
        res = self.change(current="틀린-비밀번호")
        self.assertEqual(res.status_code, 400)
        self.assertIn("current_password", res.json()["error"]["fields"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_new_password_is_checked(self):
        for new, field_message in ((OLD, "다른 비밀번호"), ("short1", "8자"), ("8402719365120", "숫자"), ("minju@example.com", "비슷한")):
            res = self.change(new=new)
            self.assertEqual(res.status_code, 400, new)
            self.assertIn(field_message, res.json()["error"]["fields"]["new_password"], new)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_repeated_wrong_passwords_are_locked(self):
        for _ in range(10):
            self.assertEqual(self.change(current="틀린-비밀번호").status_code, 400)
        res = self.change()  # 맞는 비밀번호도 잠시 받지 않는다
        self.assertEqual(res.status_code, 429)

    def test_visitor_and_missing_fields(self):
        self.assertEqual(self.change(client=APIClient()).status_code, 401)
        res = self.client.post("/api/me/password", {}, format="json")
        self.assertEqual(set(res.json()["error"]["fields"]), {"current_password", "new_password"})

    def test_member_without_password_is_sent_to_reset_mail(self):
        social = User.objects.create_user("social@example.com", None, nickname="소셜")
        client = APIClient()
        client.force_login(social)
        res = self.change(client=client)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "NO_PASSWORD")
