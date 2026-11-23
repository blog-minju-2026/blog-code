"""임시저장은 공개된 적이 없다: ever_public 을 바로잡는다.

예전에는 임시저장을 만들 때 공개 범위 기본값(공개) 때문에 ever_public 이 켜졌다. 발행한 기록은 그대로 둔다
(공개로 발행됐는지 지금은 알 수 없는 것이 섞여 있다).
"""

from django.db import migrations


def fix_drafts(apps, schema_editor):
    Post = apps.get_model("posts", "Post")
    Post.objects.filter(status="DRAFT", ever_public=True).update(ever_public=False)


class Migration(migrations.Migration):
    dependencies = [("posts", "0002_seed_topics")]

    operations = [migrations.RunPython(fix_drafts, migrations.RunPython.noop)]
