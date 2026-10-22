"""이웃 공개 기록 (POST-02): 그 한채의 이웃과 주인만 본다. 골목 · 새 기록 · 검색에는 나오지 않는다."""

from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.tests import make_member
from apps.blogs.models import Blog
from apps.community.models import Subscription

from .models import Post, Topic


class NeighborVisibilityTests(APITestCase):
    def setUp(self):
        self.owner = make_member()
        self.neighbor = make_member(email="seohyun@example.com", nickname="서현")
        self.stranger = make_member(email="jiwoo@example.com", nickname="지우")
        self.blog = Blog.objects.create(owner=self.owner, address="minju", name="민주의 한채")
        Subscription.objects.create(blog=self.blog, subscriber=self.neighbor)
        Post.objects.create(
            blog=self.blog, post_no=1, title="이웃에게만 보여 주는 일기", content="<p>한옥 마당</p>", content_text="한옥 마당",
            status="PUBLISHED", published_at=timezone.now(), visibility="SUBSCRIBERS", topic=Topic.objects.get(slug="daily"),
        )
        self.clients = {}
        for name, user in (("owner", self.owner), ("neighbor", self.neighbor), ("stranger", self.stranger)):
            client = APIClient()
            client.force_login(user)
            self.clients[name] = client
        self.clients["guest"] = APIClient()

    def test_only_neighbors_and_owner_can_open_it(self):
        for name, expected in (("owner", 200), ("neighbor", 200), ("stranger", 404), ("guest", 404)):
            res = self.clients[name].get("/api/blogs/minju/posts/1")
            self.assertEqual(res.status_code, expected, name)
        self.assertEqual(self.clients["neighbor"].get("/api/blogs/minju/posts/1").json()["visibility"], "SUBSCRIBERS")

    def test_listed_in_yard_and_neighbor_feed_only_for_those_who_can_see(self):
        for name, count in (("owner", 1), ("neighbor", 1), ("stranger", 0), ("guest", 0)):
            self.assertEqual(self.clients[name].get("/api/blogs/minju/posts").json()["total"], count, name)
        self.assertEqual(len(self.clients["neighbor"].get("/api/me/feed").json()["items"]), 1)
        self.assertEqual(len(self.clients["stranger"].get("/api/me/feed").json()["items"]), 0)

    def test_never_in_public_feeds_even_for_neighbors(self):
        for client in (self.clients["neighbor"], self.clients["owner"]):
            self.assertEqual(client.get("/api/topics/daily/posts").json()["items"], [])
            self.assertEqual(client.get("/api/home/new-posts").json()["items"], [])
            self.assertEqual(client.get("/api/search/posts", {"q": "한옥"}).json()["items"], [])

    def test_owner_can_filter_and_switch_visibility(self):
        owner = self.clients["owner"]
        self.assertEqual(owner.get("/api/blogs/minju/posts", {"visibility": "SUBSCRIBERS"}).json()["total"], 1)
        res = owner.patch("/api/blogs/minju/posts/1", {"visibility": "PUBLIC"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.clients["stranger"].get("/api/blogs/minju/posts/1").status_code, 200)
        owner.patch("/api/blogs/minju/posts/1", {"visibility": "SUBSCRIBERS"}, format="json")
        self.assertEqual(self.clients["stranger"].get("/api/blogs/minju/posts/1").status_code, 404)
