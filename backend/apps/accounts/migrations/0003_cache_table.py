"""요청 횟수 · 로그인 실패 횟수를 세는 DB 캐시 테이블 (settings.CACHES).

migrate 만으로 배포가 끝나도록 createcachetable 을 여기서 부른다. 이미 있으면 그대로 둔다.
"""

from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command("createcachetable", database=schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_verification_mail_log")]

    operations = [migrations.RunPython(create_cache_table, migrations.RunPython.noop)]
