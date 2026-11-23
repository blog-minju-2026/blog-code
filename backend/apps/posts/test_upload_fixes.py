"""사진 올리기 · 태그 · 화면 파일에서 나던 오류 고치기.

- 뒤가 잘린 JPEG 는 500 이 아니라 415 로 거절한다
- 여러 장을 담은 휴대폰 JPEG(MPO)를 받는다
- 움직이는 WebP 는 움직임을 지킨다
- DB 만 같다고 보는 태그 이름(전각 'ａｂｃ' 와 'abc')이 함께 와도 발행된다
- 화면 파일은 쓸 때마다 서버에 다시 묻게 한다 · 발행 응답의 url 은 실제로 열리는 화면 주소다
"""

import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image as PILImage
from rest_framework.test import APITestCase

from apps.accounts.tests import make_member
from apps.blogs.models import Blog

from .models import Image, Post, Tag

TEMP_MEDIA = tempfile.mkdtemp(prefix="hanchae-test-upload-fixes-")


def tearDownModule():
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


def noise(size=(640, 480)):
    """압축해도 크기가 남는 사진 (단색은 몇 바이트로 줄어 '잘린 파일'을 만들기 어렵다)."""
    return PILImage.effect_noise(size, 60).convert("RGB")


def saved(image, fmt, **kwargs):
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class UploadEdgeCaseTests(APITestCase):
    def setUp(self):
        self.client.force_authenticate(make_member())

    def upload(self, data, name="photo.jpg", content_type="image/jpeg"):
        return self.client.post("/api/images", {"file": SimpleUploadedFile(name, data, content_type)}, format="multipart")

    def test_truncated_jpeg_is_rejected_not_500(self):
        data = saved(noise(), "JPEG")
        res = self.upload(data[: len(data) * 6 // 10])
        self.assertEqual(res.status_code, 415)
        self.assertEqual(res.json()["error"]["code"], "UNSUPPORTED_FILE")
        self.assertEqual(Image.objects.count(), 0)

    def test_truncated_png_is_rejected(self):
        data = saved(noise(), "PNG")
        res = self.upload(data[: len(data) // 2], name="photo.png", content_type="image/png")
        self.assertEqual(res.status_code, 415)

    def test_multi_picture_jpeg_is_saved_as_jpeg(self):
        data = saved(noise(), "MPO", save_all=True, append_images=[noise()])
        with PILImage.open(io.BytesIO(data)) as probe:
            self.assertEqual(probe.format, "MPO")  # Pillow 는 이런 .jpg 를 MPO 로 읽는다
        res = self.upload(data)
        self.assertEqual(res.status_code, 201)
        image = Image.objects.get(pk=res.json()["id"])
        self.assertEqual(image.content_type, "image/jpeg")
        self.assertTrue(image.file.name.endswith(".jpg"))
        with PILImage.open(image.file.path) as stored:
            self.assertEqual((stored.format, stored.size), ("JPEG", (640, 480)))

    def test_animated_webp_keeps_its_frames(self):
        data = saved(noise((200, 150)), "WEBP", save_all=True, append_images=[noise((200, 150))], duration=120)
        res = self.upload(data, name="move.webp", content_type="image/webp")
        self.assertEqual(res.status_code, 201)
        image = Image.objects.get(pk=res.json()["id"])
        with PILImage.open(image.file.path) as stored:
            self.assertEqual(stored.n_frames, 2)
        with PILImage.open(image.thumb_file.path) as thumb:
            self.assertEqual(thumb.format, "WEBP")

    def test_still_webp_is_saved_again_without_metadata(self):
        res = self.upload(saved(noise((200, 150)), "WEBP"), name="still.webp", content_type="image/webp")
        self.assertEqual(res.status_code, 201)
        with PILImage.open(Image.objects.get(pk=res.json()["id"]).file.path) as stored:
            self.assertEqual(getattr(stored, "n_frames", 1), 1)


class TagCollationTests(APITestCase):
    def setUp(self):
        self.minju = make_member()
        Blog.objects.create(owner=self.minju, address="minju", name="민주의 한채")
        self.client.force_login(self.minju)

    def publish(self, tags):
        return self.client.post("/api/blogs/minju/posts", {"title": "글", "content": "<p>본문</p>", "tags": tags}, format="json")

    def test_names_only_the_database_treats_as_equal_do_not_break_publishing(self):
        # 전각 글자 · 히라가나/가타카나는 lower() 로는 다르지만 정렬 규칙(_as_ci)으로는 같은 이름일 수 있다
        for tags in (["abc", "ａｂｃ"], ["あ", "ア"]):
            res = self.publish(tags)
            self.assertEqual(res.status_code, 201, res.content)
            post = Post.objects.get(blog__address="minju", post_no=res.json()["no"])
            linked = post.post_tags.count()
            self.assertEqual(linked, Tag.objects.filter(post_tags__post=post).distinct().count())
            self.assertIn(linked, (1, 2))  # 정렬 규칙에 따라 하나로 합쳐지거나 둘로 남는다. 어느 쪽이든 발행된다

    def test_case_only_difference_is_still_one_tag(self):
        res = self.publish(["Travel", "travel"])
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Tag.objects.filter(blog__address="minju").count(), 1)


class ScreenFileTests(APITestCase):
    def test_screen_files_are_revalidated_every_time(self):
        for path in ("/", "/login", "/js/api.js", "/css/hanchae.css"):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)
            self.assertEqual(res["Cache-Control"], "no-cache", path)
            self.assertTrue(res["Last-Modified"], path)

    def test_unchanged_file_answers_304(self):
        first = self.client.get("/js/api.js")
        again = self.client.get("/js/api.js", headers={"If-Modified-Since": first["Last-Modified"]})
        self.assertEqual(again.status_code, 304)

    @override_settings(HANCHAE_DOMAIN="hanchae.java21.net")
    def test_publish_answers_the_address_the_screen_can_open(self):
        minju = make_member()
        Blog.objects.create(owner=minju, address="minju", name="민주의 한채")
        self.client.force_login(minju)
        res = self.client.post("/api/blogs/minju/posts", {"title": "글", "content": "<p>본문</p>"}, format="json")
        self.assertEqual(res.json()["url"], "/post?address=minju&no=1")
        self.assertEqual(self.client.get(res.json()["url"]).status_code, 200)
