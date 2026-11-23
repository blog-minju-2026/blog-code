"""서버 오류(500) 알림 메일: 운영 설정에서 관리자에게 가고, 같은 오류가 되풀이되면 줄인다."""

import logging
import sys

from django.core import mail
from django.test import SimpleTestCase, override_settings

from .logs import HOURLY_LIMIT, ThrottledAdminEmailHandler


def error_record(make_error):
    try:
        make_error()
    except Exception:
        return logging.LogRecord("django.request", logging.ERROR, __file__, 1, "Internal Server Error: /x", None, sys.exc_info())


def divide():
    return 1 / 0


def missing_key():
    return {}["없는 키"]


@override_settings(ADMINS=[("한채 관리자", "admin@example.com")])
class ErrorMailTests(SimpleTestCase):
    def test_django_errors_go_to_the_throttled_mail_handler(self):
        handlers = logging.getLogger("django").handlers
        self.assertTrue(any(isinstance(h, ThrottledAdminEmailHandler) for h in handlers))
        self.assertFalse(logging.getLogger("django").propagate)  # 로그 · 메일이 두 번 가지 않게

    def test_same_error_is_mailed_once_and_another_error_separately(self):
        handler = ThrottledAdminEmailHandler()
        for _ in range(5):
            handler.emit(error_record(divide))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["admin@example.com"])
        self.assertIn("ZeroDivisionError", mail.outbox[0].body)

        handler.emit(error_record(missing_key))
        self.assertEqual(len(mail.outbox), 2)

    def test_hourly_limit_caps_many_different_errors(self):
        handler = ThrottledAdminEmailHandler()
        for i in range(HOURLY_LIMIT + 5):
            # 파일 · 줄이 저마다 다른 오류
            record = logging.LogRecord("django.request", logging.ERROR, f"/app/x{i}.py", i, "오류", None, None)
            handler.emit(record)
        self.assertEqual(len(mail.outbox), HOURLY_LIMIT)

    @override_settings(ADMINS=[])
    def test_no_admins_no_mail(self):
        ThrottledAdminEmailHandler().emit(error_record(divide))
        self.assertEqual(len(mail.outbox), 0)


@override_settings(ADMINS=[("한채 관리자", "admin@example.com")])
class ServerErrorMailsAdminTests(SimpleTestCase):
    def test_unhandled_error_answers_500_json_and_mails_admins(self):
        from unittest import mock

        from django.test import Client

        with mock.patch("apps.posts.views.Topic.objects.all", side_effect=RuntimeError("일부러 낸 오류")):
            # assertLogs 로 감싸지 않는다: 감싸면 로그가 메일 처리기까지 올라가지 않는다
            res = Client(raise_request_exception=False).get("/api/topics")
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.json()["error"]["code"], "SERVER_ERROR")
        self.assertNotIn("일부러", res.content.decode())  # 응답에는 내부 정보가 없다
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].subject.startswith("[한채 오류] "))
        self.assertIn("RuntimeError", mail.outbox[0].body)
