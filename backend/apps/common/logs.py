"""서버 오류(500) 알림 메일 (settings.LOGGING 의 mail_admins).

같은 오류가 되풀이될 때 메일이 쏟아지지 않게 줄인다. 오류 메일은 인증 메일과 같은 Gmail 계정으로 나가므로,
쏟아지면 하루 발송 한도를 다 써서 가입 인증 메일까지 막힌다.

- 같은 자리에서 난 같은 종류의 오류는 SAME_ERROR_EVERY 에 한 번
- 모두 합쳐 한 시간에 HOURLY_LIMIT 번까지

횟수는 작업자(프로세스)마다 메모리에서 센다. DB 가 죽어서 나는 오류도 알려야 하므로 DB 캐시를 쓰지 않는다.
컨테이너 2개 × 작업자 3개라 실제로는 위 숫자의 최대 6배까지 갈 수 있다. 빠진 오류도 로그(docker logs)에는 모두 남는다.
"""

import time

from django.utils.log import AdminEmailHandler

SAME_ERROR_EVERY = 10 * 60
HOURLY_LIMIT = 10


class ThrottledAdminEmailHandler(AdminEmailHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_sent = {}  # 오류 자리 → 마지막으로 보낸 시각
        self._recent = []  # 최근 한 시간에 보낸 시각들

    def _signature(self, record):
        exc_type = record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else ""
        frame = None
        tb = record.exc_info[2] if record.exc_info else None
        while tb is not None:  # 오류가 실제로 난 맨 안쪽 자리
            frame = (tb.tb_frame.f_code.co_filename, tb.tb_lineno)
            tb = tb.tb_next
        return (exc_type, frame or (record.pathname, record.lineno))

    def emit(self, record):
        now = time.monotonic()
        signature = self._signature(record)
        self._recent = [t for t in self._recent if now - t < 3600]
        last = self._last_sent.get(signature)
        if (last is not None and now - last < SAME_ERROR_EVERY) or len(self._recent) >= HOURLY_LIMIT:
            return
        self._last_sent = {k: t for k, t in self._last_sent.items() if now - t < SAME_ERROR_EVERY}
        self._last_sent[signature] = now
        self._recent.append(now)
        super().emit(record)
