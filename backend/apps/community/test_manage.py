"""한채 관리 › 댓글 · 방명록 (CMT-04): 주인만, 내 한채에 남겨진 것만, 숨긴 것은 사유와 함께."""

from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.tests import make_member
from apps.blogs.models import Blog
from apps.posts.models import Post

from .models import Comment, GuestbookEntry


class ManageCommentsTests(APITestCase):
    def setUp(self):
        self.owner = make_member()
        self.reader = make_member(email="seohyun@example.com", nickname="서현")
        self.blog = Blog.objects.create(owner=self.owner, address="minju", name="민주의 한채")
        other_blog = Blog.objects.create(owner=self.reader, address="seohyun", name="서현의 한채")
        common = {"content": "x", "content_text": "x", "status": "PUBLISHED", "published_at": timezone.now()}
        self.post = Post.objects.create(blog=self.blog, post_no=1, title="처마 끝에 앉은 첫 기록", **common)
        other_post = Post.objects.create(blog=other_blog, post_no=1, title="남의 기록", **common)
        self.c1 = Comment.objects.create(post=self.post, author=self.reader, content="첫 댓글")
        self.c2 = Comment.objects.create(
            post=self.post, author=self.reader, content="도배", hidden_at=timezone.now(), hidden_reason="같은 말 되풀이"
        )
        Comment.objects.create(post=other_post, author=self.owner, content="내가 남의 기록에 남긴 것")
        self.g1 = GuestbookEntry.objects.create(blog=self.blog, author=self.reader, content="놀러 왔어요")
        GuestbookEntry.objects.create(blog=other_blog, author=self.owner, content="남의 방명록")
        self.client.force_login(self.owner)

    def test_comments_on_my_posts_newest_first_with_hidden_reason(self):
        data = self.client.get("/api/blogs/minju/manage/comments").json()
        self.assertEqual(data["total"], 2)
        first, second = data["items"]
        self.assertEqual(first["id"], self.c2.pk)
        self.assertTrue(first["hidden"])
        self.assertIsNone(first["content"])
        self.assertEqual(first["hidden_reason"], "같은 말 되풀이")
        self.assertEqual(second["content"], "첫 댓글")
        self.assertIsNone(second["hidden_reason"])
        self.assertEqual(second["post"], {"no": 1, "title": "처마 끝에 앉은 첫 기록"})
        self.assertTrue(second["can_delete"])

    def test_guestbook_received(self):
        data = self.client.get("/api/blogs/minju/manage/guestbook").json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["content"], "놀러 왔어요")

    def test_only_owner(self):
        reader = APIClient()
        reader.force_login(self.reader)
        self.assertEqual(reader.get("/api/blogs/minju/manage/comments").status_code, 403)
        self.assertEqual(reader.get("/api/blogs/minju/manage/guestbook").status_code, 403)
        self.assertEqual(APIClient().get("/api/blogs/minju/manage/comments").status_code, 401)

    def test_owner_deletes_with_existing_endpoints(self):
        self.assertEqual(self.client.delete(f"/api/comments/{self.c1.pk}").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/guestbook/{self.g1.pk}").status_code, 204)
        self.assertEqual(self.client.get("/api/blogs/minju/manage/comments").json()["total"], 1)
        self.assertEqual(self.client.get("/api/blogs/minju/manage/guestbook").json()["total"], 0)
