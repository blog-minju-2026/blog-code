"""댓글 · 공감 · 이웃 API (API 명세서 4.5 · 4.6 · 4.7)."""

from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import User
from apps.blogs.models import Blog
from apps.posts.models import Post

from .models import Comment


class CommunityApiTestBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user("minju@example.com", "password123", nickname="민주")
        self.reader = User.objects.create_user("seohyun@example.com", "password123", nickname="서현")
        self.third = User.objects.create_user("jiwon@example.com", "password123", nickname="지원")
        self.blog = Blog.objects.create(owner=self.owner, address="minju", name="민주의 한채", last_post_no=2)
        self.post = self.make_post(1, Post.Visibility.PUBLIC)
        self.secret = self.make_post(2, Post.Visibility.PRIVATE)
        self.owner_client = self.login(self.owner)
        self.reader_client = self.login(self.reader)
        self.third_client = self.login(self.third)
        self.guest = APIClient()

    def make_post(self, no, visibility):
        return Post.objects.create(
            blog=self.blog, post_no=no, title=f"기록 {no}", content="<p>본문</p>", content_text="본문",
            status=Post.Status.PUBLISHED, published_at=timezone.now(), visibility=visibility,
        )

    def login(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client


class CommentTests(CommunityApiTestBase):
    url = "/api/blogs/minju/posts/1/comments"

    def test_write_and_list(self):
        self.assertEqual(self.guest.post(self.url, {"content": "안녕"}, format="json").status_code, 401)
        res = self.reader_client.post(self.url, {"content": "  잘 읽었어요  "}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual((res.json()["content"], res.json()["author"]["nickname"]), ("잘 읽었어요", "서현"))
        listed = self.guest.get(self.url).json()
        self.assertEqual(listed["count"], 1)
        self.assertFalse(listed["items"][0]["can_delete"])
        owner_view = self.owner_client.get(self.url).json()["items"][0]
        self.assertEqual((owner_view["can_edit"], owner_view["can_delete"]), (False, True))
        self.assertEqual(self.guest.get("/api/blogs/minju/posts/1").json()["comment_count"], 1)

    def test_validation_and_token(self):
        self.assertEqual(self.reader_client.post(self.url, {"content": " "}, format="json").status_code, 400)
        self.assertEqual(self.reader_client.post(self.url, {"content": "가" * 1001}, format="json").status_code, 400)
        token = "aaaaaaaa-0d7a-4c55-9a77-1f2e3d4c5b6a"
        first = self.reader_client.post(self.url, {"content": "한 번", "client_token": token}, format="json")
        again = self.reader_client.post(self.url, {"content": "한 번", "client_token": token}, format="json")
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(Comment.objects.count(), 1)

    def test_writing_is_limited_per_member_but_reading_is_not(self):
        for i in range(10):
            self.assertEqual(self.reader_client.post(self.url, {"content": f"댓글 {i}"}, format="json").status_code, 201)
        res = self.reader_client.post(self.url, {"content": "하나 더"}, format="json")
        self.assertEqual((res.status_code, res.json()["error"]["code"]), (429, "TOO_MANY_REQUESTS"))
        self.assertEqual(self.reader_client.get(self.url).status_code, 200)
        # 다른 회원은 따로 센다
        self.assertEqual(self.third_client.post(self.url, {"content": "저도요"}, format="json").status_code, 201)

    def test_private_post_comments_are_hidden(self):
        self.assertEqual(self.reader_client.get("/api/blogs/minju/posts/2/comments").status_code, 404)
        self.assertEqual(self.owner_client.get("/api/blogs/minju/posts/2/comments").status_code, 200)

    def test_edit_only_author_delete_author_or_owner(self):
        cid = self.reader_client.post(self.url, {"content": "처음"}, format="json").json()["id"]
        self.assertEqual(self.owner_client.patch(f"/api/comments/{cid}", {"content": "주인이 고침"}, format="json").status_code, 403)
        res = self.reader_client.patch(f"/api/comments/{cid}", {"content": "고침"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(res.json()["edited_at"])
        self.assertEqual(self.third_client.delete(f"/api/comments/{cid}").status_code, 403)
        self.assertEqual(self.owner_client.delete(f"/api/comments/{cid}").status_code, 204)
        self.assertEqual(self.reader_client.delete(f"/api/comments/{cid}").status_code, 404)


class LikeTests(CommunityApiTestBase):
    url = "/api/blogs/minju/posts/1/like"

    def test_like_is_idempotent(self):
        self.assertEqual(self.guest.put(self.url).status_code, 401)
        self.reader_client.put(self.url)
        res = self.reader_client.put(self.url)
        self.assertEqual(res.json(), {"liked": True, "like_count": 1})
        detail = self.reader_client.get("/api/blogs/minju/posts/1").json()
        self.assertEqual((detail["liked_by_me"], detail["like_count"]), (True, 1))
        self.assertEqual(self.reader_client.delete(self.url).json(), {"liked": False, "like_count": 0})

    def test_cannot_like_own_or_hidden_post(self):
        self.assertEqual(self.owner_client.put(self.url).json()["error"]["code"], "NOT_ALLOWED")
        self.assertEqual(self.reader_client.put("/api/blogs/minju/posts/2/like").status_code, 404)


class SubscriptionTests(CommunityApiTestBase):
    url = "/api/blogs/minju/subscription"

    def test_subscribe_and_feed(self):
        self.assertEqual(self.owner_client.put(self.url).status_code, 422)
        self.assertEqual(self.reader_client.get("/api/me/feed").json(), {"items": [], "next_cursor": None})
        self.assertEqual(self.reader_client.put(self.url).json(), {"subscribed": True, "subscriber_count": 1})
        self.assertEqual(self.reader_client.put(self.url).json()["subscriber_count"], 1)
        blog = self.reader_client.get("/api/blogs/minju").json()
        self.assertEqual((blog["is_subscribed"], blog["subscriber_count"]), (True, 1))
        feed = self.reader_client.get("/api/me/feed?limit=3").json()
        self.assertEqual([p["no"] for p in feed["items"]], [1])  # 나만 보기는 빠진다
        self.assertEqual(self.reader_client.delete(self.url).json(), {"subscribed": False, "subscriber_count": 0})
        self.assertEqual(self.guest.get("/api/me/feed").status_code, 401)


class GuestbookTests(CommunityApiTestBase):
    url = "/api/blogs/minju/guestbook"

    def test_write_list_and_page(self):
        self.assertEqual(self.guest.post(self.url, {"content": "안녕"}, format="json").status_code, 401)
        Blog.objects.create(owner=self.reader, address="seohyun", name="서현의 한채")
        res = self.reader_client.post(self.url, {"content": "  다녀가요  "}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["content"], "다녀가요")
        self.assertEqual(res.json()["author_blog"], {"address": "seohyun", "name": "서현의 한채"})
        self.third_client.post(self.url, {"content": "두 번째"}, format="json")
        listed = self.guest.get(self.url).json()
        self.assertEqual((listed["total"], listed["items"][0]["content"]), (2, "두 번째"))  # 최신순
        self.assertIsNone(listed["items"][0]["author_blog"])
        self.assertEqual(self.reader_client.post(self.url, {"content": " "}, format="json").status_code, 400)

    def test_client_token_dedupe(self):
        token = "bbbbbbbb-0d7a-4c55-9a77-1f2e3d4c5b6a"
        first = self.reader_client.post(self.url, {"content": "한 번", "client_token": token}, format="json")
        again = self.reader_client.post(self.url, {"content": "한 번", "client_token": token}, format="json")
        self.assertEqual((first.status_code, again.status_code), (201, 200))

    def test_edit_only_author_delete_author_or_owner(self):
        eid = self.reader_client.post(self.url, {"content": "처음"}, format="json").json()["id"]
        self.assertEqual(self.owner_client.patch(f"/api/guestbook/{eid}", {"content": "주인"}, format="json").status_code, 403)
        res = self.reader_client.patch(f"/api/guestbook/{eid}", {"content": "고침"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(res.json()["edited_at"])
        self.assertEqual(self.third_client.delete(f"/api/guestbook/{eid}").status_code, 403)
        self.assertEqual(self.owner_client.delete(f"/api/guestbook/{eid}").status_code, 204)
        self.assertEqual(self.owner_client.delete(f"/api/guestbook/{eid}").status_code, 404)


class MySubscriptionsTests(CommunityApiTestBase):
    def test_list_my_neighbors(self):
        self.assertEqual(self.guest.get("/api/me/subscriptions").status_code, 401)
        jiwon = Blog.objects.create(owner=self.third, address="jiwon", name="지원의 한채")
        self.reader_client.put("/api/blogs/minju/subscription")
        self.reader_client.put("/api/blogs/jiwon/subscription")
        res = self.reader_client.get("/api/me/subscriptions").json()
        self.assertEqual([b["address"] for b in res["items"]], ["jiwon", "minju"])  # 최근 맺은 순
        self.assertEqual(res["items"][1]["post_count"], 1)  # 나만 보기는 세지 않는다
        jiwon.deleted_at = timezone.now()
        jiwon.save()
        self.assertEqual(self.reader_client.get("/api/me/subscriptions").json()["total"], 1)
