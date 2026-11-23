"""프로필 사진을 원본에서 목록용 작은 사진으로 바꿔 건다.

프로필 사진은 올린 이미지(images)의 파일 경로로 가리킨다. 예전에는 원본(최대 10MB)을 걸어서 댓글 · 목록의 작은
동그라미마다 원본이 내려갔다. 같은 이미지의 작은 사진(가로 480px WebP) 경로로 바꾼다. 파일은 건드리지 않는다.
"""

from django.db import migrations


def use_thumbs(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Image = apps.get_model("posts", "Image")
    users = User.objects.exclude(profile_image__isnull=True).exclude(profile_image="")
    thumbs = dict(
        Image.objects.filter(file__in=users.values_list("profile_image", flat=True)).values_list("file", "thumb_file")
    )
    for user in users:
        thumb = thumbs.get(user.profile_image.name)
        if thumb:
            User.objects.filter(pk=user.pk).update(profile_image=thumb)


def use_originals(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Image = apps.get_model("posts", "Image")
    users = User.objects.exclude(profile_image__isnull=True).exclude(profile_image="")
    originals = dict(
        Image.objects.filter(thumb_file__in=users.values_list("profile_image", flat=True)).values_list("thumb_file", "file")
    )
    for user in users:
        original = originals.get(user.profile_image.name)
        if original:
            User.objects.filter(pk=user.pk).update(profile_image=original)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_cache_table"), ("posts", "0001_initial")]

    operations = [migrations.RunPython(use_thumbs, use_originals)]
