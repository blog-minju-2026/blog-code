from django.conf import settings
from django.db import models
from django.db.models.functions import Coalesce


class Topic(models.Model):
    """골목 (ERD topics, REQ-007). 10개 고정이고 데이터 마이그레이션으로만 넣고 바꾼다."""

    name = models.CharField("골목 이름", max_length=20, unique=True)
    slug = models.SlugField("주소용 이름", max_length=30, unique=True)
    sort_order = models.SmallIntegerField("정렬 순서", default=0)
    created_at = models.DateTimeField("생성 일시", auto_now_add=True)
    updated_at = models.DateTimeField("수정 일시", auto_now=True)

    class Meta:
        db_table = "topics"
        ordering = ["sort_order", "id"]
        verbose_name = "골목"
        verbose_name_plural = "골목"

    def __str__(self):
        return self.name


class Category(models.Model):
    """방 (ERD categories, REQ-005).

    '모든 기록'과 '마루(미분류)'는 행으로 두지 않는다. 마루 = posts.category 가 NULL.
    같은 단계 안에서 이름이 겹치지 않도록 parent_key(최상위면 0)로 유일 제약을 건다.
    """

    blog = models.ForeignKey("blogs.Blog", on_delete=models.CASCADE, related_name="categories", verbose_name="한채")
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children", verbose_name="상위 방"
    )
    name = models.CharField("방 이름", max_length=20)
    sort_order = models.IntegerField("순서", default=0)
    parent_key = models.GeneratedField(
        expression=Coalesce(models.F("parent_id"), models.Value(0)),
        output_field=models.BigIntegerField(),
        db_persist=True,
        verbose_name="같은 단계 이름 중복 검사용",
    )
    created_at = models.DateTimeField("생성 일시", auto_now_add=True)
    updated_at = models.DateTimeField("수정 일시", auto_now=True)

    class Meta:
        db_table = "categories"
        ordering = ["sort_order", "id"]
        verbose_name = "방"
        verbose_name_plural = "방"
        constraints = [
            models.UniqueConstraint(fields=["blog", "parent_key", "name"], name="uk_categories_name"),
        ]

    def __str__(self):
        return self.name


class Tag(models.Model):
    """태그 (ERD tags, REQ-006). 한채 단위. 영문 대소문자만 다른 이름은 DB 정렬 규칙(_ci) 때문에 같은 태그다."""

    blog = models.ForeignKey("blogs.Blog", on_delete=models.CASCADE, related_name="tags", verbose_name="한채")
    name = models.CharField("태그 이름", max_length=20)
    created_at = models.DateTimeField("생성 일시", auto_now_add=True)

    class Meta:
        db_table = "tags"
        verbose_name = "태그"
        verbose_name_plural = "태그"
        constraints = [
            models.UniqueConstraint(fields=["blog", "name"], name="uk_tags_name"),
        ]

    def __str__(self):
        return self.name


class Image(models.Model):
    """본문 이미지 (ERD images, REQ-004). 하루가 지나도 어디에도 쓰이지 않으면 정리 작업이 지운다 (posts/cleanup.py)."""

    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="images", verbose_name="올린 회원"
    )
    file = models.ImageField("저장 경로", max_length=255, upload_to="images/%Y/%m/")
    thumb_file = models.ImageField("목록용 작은 이미지", max_length=255, upload_to="images/thumbs/%Y/%m/")
    content_type = models.CharField("형식", max_length=20)
    width = models.PositiveIntegerField("가로")
    height = models.PositiveIntegerField("세로")
    size_bytes = models.PositiveIntegerField("크기(바이트)")
    created_at = models.DateTimeField("생성 일시", auto_now_add=True)

    class Meta:
        db_table = "images"
        verbose_name = "이미지"
        verbose_name_plural = "이미지"

    def __str__(self):
        return self.file.name


class Post(models.Model):
    """기록 (ERD posts, REQ-004).

    글 주소는 한채마다 1부터 매기는 post_no 이고, 처음 발행할 때 blogs.last_post_no 를 올려 정한다.
    published_at 은 처음 공개된 시각이라 수정해도 바뀌지 않는다.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "임시저장"
        PUBLISHED = "PUBLISHED", "발행"

    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", "공개"
        SUBSCRIBERS = "SUBSCRIBERS", "이웃 공개"
        PRIVATE = "PRIVATE", "나만 보기"

    blog = models.ForeignKey("blogs.Blog", on_delete=models.CASCADE, related_name="posts", verbose_name="한채")
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="posts", verbose_name="방"
    )
    topic = models.ForeignKey(
        Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="posts", verbose_name="골목"
    )
    post_no = models.PositiveIntegerField("한채 안 글 번호", null=True, blank=True)
    title = models.CharField("제목", max_length=100, blank=True, default="")
    content = models.TextField("본문(정제한 HTML)")
    content_text = models.TextField("서식 뺀 본문")
    excerpt = models.CharField("요약", max_length=150, blank=True, default="")
    status = models.CharField("상태", max_length=10, choices=Status.choices, default=Status.DRAFT)
    visibility = models.CharField("공개 범위", max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC)
    published_at = models.DateTimeField("발행일", null=True, blank=True)
    ever_public = models.BooleanField("한 번이라도 공개됨", default=False)
    view_count = models.PositiveIntegerField("조회수", default=0)
    cover_image = models.ForeignKey(
        Image, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="대표 이미지"
    )
    first_image = models.ForeignKey(
        Image, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="본문 첫 이미지"
    )
    hidden_at = models.DateTimeField("관리자 숨김 시각", null=True, blank=True)
    hidden_reason = models.CharField("숨김 사유", max_length=200, null=True, blank=True)
    hidden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="숨긴 관리자",
    )
    client_token = models.CharField("발행 중복 방지 토큰", max_length=36, null=True, blank=True)
    created_at = models.DateTimeField("생성 일시", auto_now_add=True)
    updated_at = models.DateTimeField("수정 일시", auto_now=True)

    class Meta:
        db_table = "posts"
        verbose_name = "기록"
        verbose_name_plural = "기록"
        constraints = [
            models.UniqueConstraint(fields=["blog", "post_no"], name="uk_posts_post_no"),
            models.UniqueConstraint(fields=["blog", "client_token"], name="uk_posts_client_token"),
            models.CheckConstraint(condition=models.Q(status__in=["DRAFT", "PUBLISHED"]), name="ck_posts_status"),
            models.CheckConstraint(
                condition=models.Q(visibility__in=["PUBLIC", "SUBSCRIBERS", "PRIVATE"]), name="ck_posts_visibility"
            ),
            models.CheckConstraint(
                condition=models.Q(status="DRAFT")
                | (models.Q(post_no__isnull=False) & models.Q(published_at__isnull=False)),
                name="ck_posts_published_fields",
            ),
            models.CheckConstraint(
                condition=models.Q(hidden_at__isnull=True) | models.Q(hidden_reason__isnull=False),
                name="ck_posts_hidden_reason",
            ),
        ]
        indexes = [
            models.Index(fields=["blog", "status", "published_at", "id"], name="idx_posts_blog_list"),
            models.Index(fields=["status", "visibility", "published_at", "id"], name="idx_posts_home"),
            models.Index(fields=["topic", "published_at", "id"], name="idx_posts_topic"),
            models.Index(fields=["category", "published_at", "id"], name="idx_posts_category"),
        ]

    def __str__(self):
        return self.title or f"(제목 없음 #{self.pk})"


class PostTag(models.Model):
    """글-태그 연결 (ERD post_tags). 글당 최대 10개는 앱에서 검사한다."""

    pk = models.CompositePrimaryKey("post_id", "tag_id")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="post_tags")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="post_tags")

    class Meta:
        db_table = "post_tags"
        verbose_name = "글-태그 연결"
        verbose_name_plural = "글-태그 연결"


class PostImage(models.Model):
    """글-이미지 연결 (ERD post_images). 글을 저장할 때 본문에 남은 이미지 기준으로 다시 만든다."""

    pk = models.CompositePrimaryKey("post_id", "image_id")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="post_images")
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name="post_images")

    class Meta:
        db_table = "post_images"
        verbose_name = "글-이미지 연결"
        verbose_name_plural = "글-이미지 연결"


class PostView(models.Model):
    """조회 기록 (ERD post_views, REQ-008). 같은 방문자가 30분 안에 다시 연 글은 남기지 않는다."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="views", verbose_name="기록")
    viewer_key = models.CharField("방문자 키(SHA-256)", max_length=64)
    viewed_at = models.DateTimeField("조회 시각")

    class Meta:
        db_table = "post_views"
        verbose_name = "조회 기록"
        verbose_name_plural = "조회 기록"
        indexes = [
            models.Index(fields=["post", "viewer_key", "viewed_at"], name="idx_post_views_dedup"),
            models.Index(fields=["viewed_at", "post"], name="idx_post_views_window"),
        ]
