"""기록 · 방 · 태그 · 마을 목록 API (API 명세서 4.3 · 4.4 · 4.9)."""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import User
from apps.blogs.models import Blog

from .models import Category, Post, PostImage, Tag
from .tests import png_bytes

TEMP_MEDIA = tempfile.mkdtemp(prefix="hanchae-test-media-")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PostApiTestBase(APITestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.owner = User.objects.create_user("minju@example.com", "password123", nickname="민주")
        self.reader = User.objects.create_user("seohyun@example.com", "password123", nickname="서현")
        self.blog = Blog.objects.create(owner=self.owner, address="minju", name="민주의 한채")
        self.client.force_authenticate(self.owner)
        self.guest = APIClient()
        self.other = APIClient()
        self.other.force_authenticate(self.reader)

    def publish(self, client=None, **extra):
        data = {"title": "첫 기록", "content": "<p>본문입니다</p>", **extra}
        return (client or self.client).post("/api/blogs/minju/posts", data, format="json")


class PublishTests(PostApiTestBase):
    def test_publish_numbers_posts_and_cleans_html(self):
        res = self.publish(content='<p onclick="x()">안녕<script>alert(1)</script></p>')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["no"], 1)
        self.assertEqual(self.publish().json()["no"], 2)
        post = Post.objects.get(blog=self.blog, post_no=1)
        self.assertEqual(post.content, "<p>안녕</p>")
        self.assertEqual((post.content_text, post.excerpt), ("안녕", "안녕"))
        self.assertEqual(post.status, Post.Status.PUBLISHED)
        self.assertTrue(post.ever_public)

    def test_only_owner_can_publish(self):
        self.assertEqual(self.publish(self.guest).status_code, 401)
        self.assertEqual(self.publish(self.other).status_code, 403)

    def test_title_and_body_are_required(self):
        res = self.publish(title="  ", content="<p> </p>")
        self.assertEqual(res.status_code, 400)
        self.assertIn("title", res.json()["error"]["fields"])
        res = self.publish(content="<script>x</script>")
        self.assertEqual(res.json()["error"]["fields"]["content"], "본문을 써 주세요.")

    def test_same_client_token_returns_first_post(self):
        token = "6f1c2b9e-0d7a-4c55-9a77-1f2e3d4c5b6a"
        first = self.publish(client_token=token)
        again = self.publish(client_token=token, title="두 번 누름")
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(again.json()["no"], first.json()["no"])
        self.assertEqual(Post.objects.count(), 1)

    def test_tags_ignore_case_and_max_ten(self):
        self.publish(tags=["Django", "#django", "쿠키", " "])
        self.assertEqual(sorted(Tag.objects.values_list("name", flat=True)), ["Django", "쿠키"])
        res = self.publish(tags=[f"t{i}" for i in range(11)])
        self.assertEqual(res.status_code, 400)

    def test_neighbor_visibility_can_be_published(self):
        self.assertEqual(self.publish(visibility="SUBSCRIBERS").status_code, 201)
        self.assertEqual(Post.objects.get(post_no=1).visibility, "SUBSCRIBERS")

    def test_room_must_be_mine_and_topic_must_exist(self):
        other_blog = Blog.objects.create(owner=self.reader, address="seohyun", name="서현의 한채")
        foreign = Category.objects.create(blog=other_blog, name="남의 방")
        self.assertIn("category_id", self.publish(category_id=foreign.pk).json()["error"]["fields"])
        self.assertIn("topic_slug", self.publish(topic_slug="nope").json()["error"]["fields"])

    def test_body_images_are_linked_and_outside_images_dropped(self):
        up = self.client.post("/api/images", {"file": SimpleUploadedFile("a.png", png_bytes(), "image/png")}, format="multipart").json()
        content = f'<p>사진</p><img src="{up["url"]}"><img src="https://evil.example/t.png">'
        self.publish(content=content)
        post = Post.objects.get(post_no=1)
        self.assertNotIn("evil.example", post.content)
        self.assertEqual(post.first_image_id, up["id"])
        self.assertEqual(PostImage.objects.filter(post=post).count(), 1)
        item = self.guest.get("/api/blogs/minju/posts").json()["items"][0]
        self.assertTrue(item["thumbnail_url"].endswith(".webp"))


class ReadTests(PostApiTestBase):
    def setUp(self):
        super().setUp()
        self.dev = Category.objects.create(blog=self.blog, name="개발")
        self.publish(title="공개 개발", category_id=self.dev.pk, tags=["Django"], topic_slug="it")
        self.publish(title="공개 마루", content="<p>쿠키 이야기</p>")
        self.publish(title="나만 보기", visibility="PRIVATE")

    def titles(self, res):
        return [p["title"] for p in res.json()["items"]]

    def test_guest_sees_only_public_and_owner_sees_all(self):
        guest = self.guest.get("/api/blogs/minju/posts").json()
        self.assertEqual((guest["total"], guest["total_pages"]), (2, 1))
        self.assertNotIn("view_count", guest["items"][0])
        owner = self.client.get("/api/blogs/minju/posts").json()
        self.assertEqual(self.titles(self.client.get("/api/blogs/minju/posts")), ["나만 보기", "공개 마루", "공개 개발"])
        self.assertIn("view_count", owner["items"][0])
        self.assertEqual(self.guest.get("/api/blogs/minju/posts/3").status_code, 404)

    def test_filters(self):
        get = lambda q: self.titles(self.guest.get(f"/api/blogs/minju/posts?{q}"))  # noqa: E731
        self.assertEqual(get(f"category={self.dev.pk}"), ["공개 개발"])
        self.assertEqual(get("category=none"), ["공개 마루"])
        self.assertEqual(get("tag=django"), ["공개 개발"])
        self.assertEqual(get("q=쿠키"), ["공개 마루"])
        self.assertEqual(self.guest.get("/api/blogs/minju/posts?q=%20").status_code, 400)
        self.assertEqual(get("page=9"), [])

    def test_detail_has_neighbors_tags_and_room(self):
        body = self.guest.get("/api/blogs/minju/posts/2").json()
        self.assertEqual(body["prev"], {"no": 1, "title": "공개 개발"})
        self.assertIsNone(body["next"])  # 3번은 나만 보기라 손님에게는 없다
        first = self.guest.get("/api/blogs/minju/posts/1").json()
        self.assertEqual((first["tags"], first["category"]["name"], first["topic"]["slug"]), (["Django"], "개발", "it"))
        self.assertFalse(first["is_owner"])

    def test_patch_keeps_number_and_date(self):
        before = Post.objects.get(post_no=1)
        res = self.client.patch("/api/blogs/minju/posts/1", {"title": "고친 제목", "tags": ["새태그"], "category_id": None}, format="json")
        self.assertEqual(res.status_code, 200)
        after = Post.objects.get(post_no=1)
        self.assertEqual((after.title, after.category, after.published_at), ("고친 제목", None, before.published_at))
        self.assertEqual(self.guest.get("/api/blogs/minju/posts/1").json()["tags"], ["새태그"])
        self.assertEqual(self.other.patch("/api/blogs/minju/posts/1", {"title": "x"}, format="json").status_code, 403)

    def test_delete_does_not_reuse_number(self):
        self.assertEqual(self.other.delete("/api/blogs/minju/posts/3").status_code, 403)
        self.assertEqual(self.client.delete("/api/blogs/minju/posts/3").status_code, 204)
        self.assertEqual(self.publish().json()["no"], 4)

    def test_view_count_dedup_and_owner_not_counted(self):
        for _ in range(2):
            self.assertEqual(self.guest.post("/api/blogs/minju/posts/1/views").status_code, 204)
        self.client.post("/api/blogs/minju/posts/1/views")
        self.other.post("/api/blogs/minju/posts/1/views")
        self.assertEqual(Post.objects.get(post_no=1).view_count, 2)  # 손님 1 + 서현 1

    def test_categories_and_tags(self):
        rooms = self.guest.get("/api/blogs/minju/categories").json()
        self.assertEqual(rooms, {"total_count": 2, "rooms": [{"id": self.dev.pk, "name": "개발", "post_count": 1}], "uncategorized_count": 1})
        self.assertEqual(self.client.post("/api/blogs/minju/categories", {"name": "여행"}, format="json").status_code, 201)
        self.assertEqual(self.client.post("/api/blogs/minju/categories", {"name": "여행"}, format="json").status_code, 409)
        self.assertEqual(self.other.post("/api/blogs/minju/categories", {"name": "x"}, format="json").status_code, 403)
        self.assertEqual(self.guest.get("/api/blogs/minju/tags").json(), [{"name": "Django", "post_count": 1}])

    def test_village_lists_use_cursor(self):
        first = self.guest.get("/api/home/new-posts?limit=1").json()
        self.assertEqual(self.titles_of(first), ["공개 마루"])
        second = self.guest.get(f"/api/home/new-posts?limit=1&cursor={first['next_cursor']}").json()
        self.assertEqual(self.titles_of(second), ["공개 개발"])
        self.assertIsNone(second["next_cursor"])
        self.assertEqual(self.titles_of(self.guest.get("/api/topics/it/posts").json()), ["공개 개발"])
        self.assertEqual(self.guest.get("/api/topics/nope/posts").status_code, 404)

    def titles_of(self, body):
        return [p["title"] for p in body["items"]]
