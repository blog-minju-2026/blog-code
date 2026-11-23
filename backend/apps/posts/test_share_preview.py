"""링크 미리보기: 기록 · 마당 화면의 <head> 에 누구나 볼 수 있는 기록 · 한채의 제목과 og 태그를 채운다."""

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.tests import make_member
from apps.blogs.models import Blog
from apps.moderation.models import UserSanction

from .models import Image, Post


class SharePreviewTests(APITestCase):
    def setUp(self):
        self.minju = make_member()
        self.blog = Blog.objects.create(owner=self.minju, address="minju", name="민주의 한채", description="천천히 쌓는 기록", last_post_no=3)
        self.image = Image.objects.create(
            uploader=self.minju, file="images/2026/11/a.jpg", thumb_file="images/thumbs/2026/11/a.webp",
            content_type="image/jpeg", width=800, height=600, size_bytes=1000,
        )
        self.post = self.make_post(1, title='가을 <산책> & "단풍"', first_image=self.image)

    def make_post(self, no, visibility=Post.Visibility.PUBLIC, **extra):
        values = {
            "title": f"기록 {no}", "content": "<p>본문</p>", "content_text": "본문", "excerpt": "단풍이 든 길을 걸었다",
            "status": Post.Status.PUBLISHED, "published_at": timezone.now(), "visibility": visibility, **extra,
        }
        return Post.objects.create(blog=self.blog, post_no=no, **values)

    def page(self, path):
        res = self.client.get(path)
        self.assertEqual(res.status_code, 200)
        # 미리보기를 채우지 않은 화면은 파일 그대로(FileResponse) 나간다
        body = b"".join(res.streaming_content) if res.streaming else res.content
        return body.decode()

    def test_public_post_fills_title_and_og_tags(self):
        html = self.page("/post?address=minju&no=1")
        self.assertIn("<title>가을 &lt;산책&gt; &amp; &quot;단풍&quot; · 민주의 한채</title>", html)
        self.assertIn('<meta property="og:title" content="가을 &lt;산책&gt; &amp; &quot;단풍&quot;">', html)
        self.assertIn('<meta property="og:description" content="단풍이 든 길을 걸었다">', html)
        self.assertIn('<meta property="og:type" content="article">', html)
        self.assertIn('<meta property="og:url" content="http://testserver/post?address=minju&amp;no=1">', html)
        self.assertIn('<meta property="og:image" content="http://testserver/media/images/2026/11/a.jpg">', html)
        self.assertNotIn("<산책>", html)  # 제목이 태그로 들어가지 않는다
        # 화면 파일의 나머지는 그대로다
        self.assertIn('<script src="js/pages/post.js"></script>', html)
        self.assertEqual(html.count("<title>"), 1)

    def test_cover_image_wins_and_post_without_image_has_no_og_image(self):
        cover = Image.objects.create(
            uploader=self.minju, file="images/2026/11/cover.png", thumb_file="images/thumbs/2026/11/cover.webp",
            content_type="image/png", width=800, height=600, size_bytes=1000,
        )
        Post.objects.filter(pk=self.post.pk).update(cover_image=cover)
        self.assertIn("/media/images/2026/11/cover.png", self.page("/post?address=minju&no=1"))
        self.make_post(2)
        html = self.page("/post?address=minju&no=2")
        self.assertIn('og:title" content="기록 2"', html)
        self.assertNotIn("og:image", html)

    def test_posts_not_open_to_everyone_keep_the_plain_page(self):
        self.make_post(2, Post.Visibility.PRIVATE, title="비밀 일기")
        self.make_post(3, Post.Visibility.SUBSCRIBERS, title="이웃에게만")
        Post.objects.create(blog=self.blog, title="쓰는 중", content="", content_text="", status=Post.Status.DRAFT)
        hidden = self.make_post(4, title="숨긴 기록")
        Post.objects.filter(pk=hidden.pk).update(hidden_at=timezone.now(), hidden_reason="사유")
        self.client.force_login(self.minju)  # 주인이 열어도 미리보기는 채우지 않는다 (주소만 읽는 로봇과 같은 내용)
        for no, secret in ((2, "비밀 일기"), (3, "이웃에게만"), (4, "숨긴 기록"), (99, "기록 99")):
            html = self.page(f"/post?address=minju&no={no}")
            self.assertIn("<title>한채 · 기록</title>", html, no)
            self.assertNotIn("og:title", html, no)
            self.assertNotIn(secret, html, no)

    def test_closed_house_keeps_the_plain_page(self):
        UserSanction.objects.create(user=self.minju, admin=make_member("admin@example.com", "관리인"), reason="사유", starts_at=timezone.now())
        for path in ("/post?address=minju&no=1", "/yard?address=minju"):
            self.assertNotIn("og:title", self.page(path), path)

    def test_yard_fills_house_name_and_description(self):
        html = self.page("/yard?address=minju")
        self.assertIn("<title>민주의 한채 · 한채</title>", html)
        self.assertIn('<meta property="og:title" content="민주의 한채">', html)
        self.assertIn('<meta property="og:description" content="천천히 쌓는 기록">', html)
        self.assertIn('<meta property="og:url" content="http://testserver/yard?address=minju">', html)
        self.assertIn('<meta property="og:type" content="website">', html)

    def test_odd_query_values_open_the_plain_page(self):
        for path in ("/post", "/post?address=minju", "/post?address=minju&no=abc", "/post?address=minju&no=²", "/post?address=MINJU&no=1",
                     "/post?address=minju&no=99999999999999999999", "/yard?address=없는집", "/yard?address=", "/post?address=%00&no=1"):
            html = self.page(path)
            self.assertNotIn("og:title", html, path)

    def test_other_pages_are_not_touched(self):
        self.assertNotIn("og:title", self.page("/guestbook?address=minju"))
        self.assertEqual(self.client.get("/post?address=minju&no=1")["Cache-Control"], "no-cache")
