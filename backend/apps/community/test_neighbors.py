"""한채 관리 › 이웃 (SUB-04): 주인이 이웃을 보고, 내보내고, 다시 받아 준다."""

from apps.accounts.withdrawal import withdraw
from apps.blogs.demolish import demolish_blogs
from apps.blogs.models import Blog
from apps.posts.models import Post

from .models import BlockedNeighbor, Subscription
from .test_api import CommunityApiTestBase


class ManageNeighborsTests(CommunityApiTestBase):
    def setUp(self):
        super().setUp()
        self.neighbors_only = self.make_post(3, Post.Visibility.SUBSCRIBERS)
        self.reader_client.put("/api/blogs/minju/subscription")
        self.third_client.put("/api/blogs/minju/subscription")

    def neighbors(self):
        return self.owner_client.get("/api/blogs/minju/manage/neighbors").json()

    def kick(self, nickname="서현"):
        row = next(n for n in self.neighbors()["items"] if n["user"]["nickname"] == nickname)
        return self.owner_client.delete(f"/api/blogs/minju/manage/neighbors/{row['id']}")

    def test_owner_sees_neighbors_newest_first(self):
        body = self.neighbors()
        self.assertEqual(body["total"], 2)
        self.assertEqual([n["user"]["nickname"] for n in body["items"]], ["지원", "서현"])
        self.assertEqual(set(body["items"][0]), {"id", "user", "since"})

    def test_only_owner_manages_neighbors(self):
        for path in ("/api/blogs/minju/manage/neighbors", "/api/blogs/minju/manage/blocked-neighbors"):
            self.assertEqual(self.guest.get(path).status_code, 401)
            self.assertEqual(self.reader_client.get(path).status_code, 403)
        sub = Subscription.objects.get(subscriber=self.third)
        self.assertEqual(self.reader_client.delete(f"/api/blogs/minju/manage/neighbors/{sub.pk}").status_code, 403)
        self.assertTrue(Subscription.objects.filter(pk=sub.pk).exists())

    def test_kicked_neighbor_loses_neighbor_only_posts_and_cannot_come_back(self):
        self.assertEqual(self.reader_client.get("/api/blogs/minju/posts/3").status_code, 200)

        res = self.kick()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"subscriber_count": 1})
        self.assertEqual(self.reader_client.get("/api/blogs/minju/posts/3").status_code, 404)
        self.assertFalse(self.reader_client.get("/api/blogs/minju").json()["is_subscribed"])

        again = self.reader_client.put("/api/blogs/minju/subscription")
        self.assertEqual(again.status_code, 403)
        self.assertEqual(again.json()["error"]["code"], "NEIGHBOR_BLOCKED")
        self.assertFalse(Subscription.objects.filter(blog=self.blog, subscriber=self.reader).exists())
        # 다른 이웃은 그대로다
        self.assertEqual(self.third_client.get("/api/blogs/minju/posts/3").status_code, 200)

    def test_owner_lets_a_kicked_neighbor_back(self):
        self.kick()
        blocked = self.owner_client.get("/api/blogs/minju/manage/blocked-neighbors").json()
        self.assertEqual([b["user"]["nickname"] for b in blocked["items"]], ["서현"])

        res = self.owner_client.delete(f"/api/blogs/minju/manage/blocked-neighbors/{blocked['items'][0]['id']}")
        self.assertEqual(res.status_code, 204)
        # 다시 받아 줘도 저절로 이웃이 되지는 않는다. 그 회원이 다시 맺어야 한다
        self.assertFalse(Subscription.objects.filter(blog=self.blog, subscriber=self.reader).exists())
        self.assertEqual(self.reader_client.put("/api/blogs/minju/subscription").status_code, 200)
        self.assertEqual(self.reader_client.get("/api/blogs/minju/posts/3").status_code, 200)

    def test_unknown_rows_are_404(self):
        self.assertEqual(self.owner_client.delete("/api/blogs/minju/manage/neighbors/999999").status_code, 404)
        self.assertEqual(self.owner_client.delete("/api/blogs/minju/manage/blocked-neighbors/999999").status_code, 404)
        # 다른 한채의 이웃 번호로는 내보낼 수 없다
        other = Blog.objects.create(owner=self.reader, address="seohyun", name="서현의 한채")
        sub = Subscription.objects.create(blog=other, subscriber=self.third)
        self.assertEqual(self.owner_client.delete(f"/api/blogs/minju/manage/neighbors/{sub.pk}").status_code, 404)
        self.assertTrue(Subscription.objects.filter(pk=sub.pk).exists())

    def test_kicking_twice_keeps_one_mark(self):
        self.kick()
        Subscription.objects.create(blog=self.blog, subscriber=self.reader)  # 막는 표시가 있는데 이웃 행이 남은 경우
        self.kick()
        self.assertEqual(BlockedNeighbor.objects.filter(blog=self.blog, user=self.reader).count(), 1)

    def test_marks_are_removed_with_the_house_and_the_member(self):
        self.kick("서현")
        self.kick("지원")
        withdraw(self.reader)
        self.assertEqual(list(BlockedNeighbor.objects.values_list("user__nickname", flat=True)), ["지원"])
        demolish_blogs([self.blog], self.owner)
        self.assertEqual(BlockedNeighbor.objects.count(), 0)
