"""임시저장 (POST-11): 주인만 보고, 이어 쓰고, 발행하면 번호를 받아 공개된다."""

import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.tests import make_member
from apps.blogs.models import Blog

from .cleanup import delete_unused_images
from .models import Image, Post
from .tests import png_bytes

TEMP_MEDIA = tempfile.mkdtemp(prefix="hanchae-test-drafts-")


def tearDownModule():
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DraftTests(APITestCase):
    def setUp(self):
        self.owner = make_member()
        self.reader = make_member(email="seohyun@example.com", nickname="서현")
        self.blog = Blog.objects.create(owner=self.owner, address="minju", name="민주의 한채")
        self.client.force_login(self.owner)
        self.url = "/api/blogs/minju/drafts"

    def test_save_empty_then_continue_and_list(self):
        res = self.client.post(self.url, {}, format="json")
        self.assertEqual(res.status_code, 201)
        draft_id = res.json()["id"]
        draft = Post.objects.get(pk=draft_id)
        self.assertEqual(draft.status, "DRAFT")
        self.assertIsNone(draft.post_no)

        res = self.client.patch(f"{self.url}/{draft_id}", {"title": "제주 돌담길", "content": "<p>돌담 사이로</p>", "tags": ["제주"]}, format="json")
        self.assertEqual(res.status_code, 200)
        detail = self.client.get(f"{self.url}/{draft_id}").json()
        self.assertEqual(detail["title"], "제주 돌담길")
        self.assertEqual(detail["tags"], ["제주"])
        self.assertEqual(detail["visibility"], "PUBLIC")

        items = self.client.get(self.url).json()["items"]
        self.assertEqual([d["id"] for d in items], [draft_id])
        self.assertEqual(items[0]["content_length"], len("돌담 사이로"))

    def test_drafts_are_owner_only_and_never_public(self):
        draft_id = self.client.post(self.url, {"title": "비밀 초안", "content": "<p>한옥</p>"}, format="json").json()["id"]
        reader = APIClient()
        reader.force_login(self.reader)
        self.assertEqual(reader.get(self.url).status_code, 403)
        self.assertEqual(reader.get(f"{self.url}/{draft_id}").status_code, 403)
        self.assertEqual(APIClient().get(self.url).status_code, 401)
        # 마당 목록 · 개수 · 검색 · 태그에 나오지 않는다
        self.assertEqual(self.client.get("/api/blogs/minju/posts").json()["total"], 0)
        self.assertEqual(APIClient().get("/api/blogs/minju").json()["post_count"], 0)
        self.assertEqual(APIClient().get("/api/search/posts", {"q": "한옥"}).json()["items"], [])

    def test_publish_gives_number_and_shows_up(self):
        draft_id = self.client.post(self.url, {"title": "", "content": ""}, format="json").json()["id"]
        # 발행은 새 기록과 같은 검사: 제목 · 본문이 있어야 한다
        self.assertEqual(self.client.post(f"{self.url}/{draft_id}/publish", {"title": "", "content": ""}, format="json").status_code, 400)
        self.client.post("/api/blogs/minju/posts", {"title": "먼저 쓴 글", "content": "<p>a</p>"}, format="json")

        res = self.client.post(f"{self.url}/{draft_id}/publish", {"title": "제주 돌담길", "content": "<p>돌담</p>", "visibility": "PUBLIC"}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["no"], 2)
        post = Post.objects.get(pk=draft_id)
        self.assertEqual((post.status, post.post_no), ("PUBLISHED", 2))
        self.assertIsNotNone(post.published_at)
        self.assertEqual(APIClient().get("/api/blogs/minju/posts/2").json()["title"], "제주 돌담길")
        self.assertEqual(self.client.get(self.url).json()["total"], 0)
        # 이미 발행했으면 다시 발행할 수 없다
        self.assertEqual(self.client.post(f"{self.url}/{draft_id}/publish", {"title": "x", "content": "<p>x</p>"}, format="json").status_code, 404)

    def test_published_post_is_not_a_draft(self):
        self.client.post("/api/blogs/minju/posts", {"title": "글", "content": "<p>a</p>"}, format="json")
        post_id = Post.objects.get().pk
        self.assertEqual(self.client.get(f"{self.url}/{post_id}").status_code, 404)
        self.assertEqual(self.client.delete(f"{self.url}/{post_id}").status_code, 404)
        self.assertTrue(Post.objects.filter(pk=post_id).exists())

    def test_draft_photos_survive_cleanup(self):
        up = self.client.post("/api/images", {"file": SimpleUploadedFile("a.png", png_bytes(), "image/png")}, format="multipart").json()
        self.client.post(self.url, {"content": f'<p><img src="{up["url"]}"></p>'}, format="json")
        Image.objects.filter(pk=up["id"]).update(created_at=timezone.now() - timedelta(days=2))
        self.assertEqual(delete_unused_images(), 0)
        self.assertTrue(Image.objects.filter(pk=up["id"]).exists())

    def test_delete(self):
        draft_id = self.client.post(self.url, {"title": "버릴 초안"}, format="json").json()["id"]
        self.assertEqual(self.client.delete(f"{self.url}/{draft_id}").status_code, 204)
        self.assertFalse(Post.objects.filter(pk=draft_id).exists())
