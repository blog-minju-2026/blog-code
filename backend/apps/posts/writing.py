"""기록 발행 · 수정에서 쓰는 저장 규칙 (API 명세서 4.3, ERD REQ-004 · REQ-006)."""

from django.utils import timezone

from apps.common.errors import APIError

from . import content as body
from .models import Category, Image, Post, PostImage, PostTag, Tag, Topic


def find_category(blog, category_id):
    if category_id is None:
        return None  # 마루
    category = Category.objects.filter(pk=category_id, blog=blog).first()
    if category is None:
        raise APIError(400, "VALIDATION_ERROR", "입력한 내용을 확인해 주세요.", fields={"category_id": "이 한채에 없는 방이에요."})
    return category


def find_topic(slug):
    if not slug:
        return None
    topic = Topic.objects.filter(slug=slug).first()
    if topic is None:
        raise APIError(400, "VALIDATION_ERROR", "입력한 내용을 확인해 주세요.", fields={"topic_slug": "없는 골목이에요."})
    return topic


def find_cover(image_id, owner):
    if image_id is None:
        return None
    image = Image.objects.filter(pk=image_id, uploader=owner).first()
    if image is None:
        raise APIError(400, "VALIDATION_ERROR", "입력한 내용을 확인해 주세요.", fields={"cover_image_id": "먼저 사진을 올려 주세요."})
    return image


def apply_fields(post, data, blog, allow_empty=False):
    """요청에 온 칸만 글에 옮긴다. 본문은 정제하고 요약 · 글자 · 첫 사진을 다시 만든다.

    allow_empty: 임시저장은 본문이 비어 있어도 된다 (발행할 때 다시 검사한다).
    """
    if "title" in data:
        post.title = data["title"]
    if "content" in data:
        post.content = body.sanitize(data["content"])
        post.content_text = body.to_text(post.content)
        if not allow_empty and not post.content_text and "<img" not in post.content:
            raise APIError(400, "VALIDATION_ERROR", "입력한 내용을 확인해 주세요.", fields={"content": "본문을 써 주세요."})
        post.excerpt = body.excerpt(post.content_text)
    if "category_id" in data:
        post.category = find_category(blog, data["category_id"])
    if "topic_slug" in data:
        post.topic = find_topic(data["topic_slug"])
    if "visibility" in data:
        post.visibility = data["visibility"]
        if post.visibility == Post.Visibility.PUBLIC:
            post.ever_public = True
    if "cover_image_id" in data:
        post.cover_image = find_cover(data["cover_image_id"], blog.owner)


def link_images(post, owner):
    """본문에 남아 있는 사진(주인이 올린 것)으로 글-이미지 연결과 본문 첫 사진을 다시 정한다.

    화면이 보낸 image_ids 대신 정제한 본문을 기준으로 삼는다. 본문에서 지운 사진이 연결로 남지 않게 하려고.
    """
    paths = body.image_paths(post.content)
    images = {img.file.name: img for img in Image.objects.filter(uploader=owner, file__in=paths)}
    ordered = [images[p] for p in paths if p in images]
    post.first_image = ordered[0] if ordered else None
    PostImage.objects.filter(post=post).delete()
    PostImage.objects.bulk_create([PostImage(post=post, image=img) for img in ordered])


def set_tags(post, names):
    """글의 태그를 names 로 바꾼다. 없던 이름이면 그 한채에 새로 만든다 (대소문자 무시)."""
    tags = []
    for name in names:
        tag = Tag.objects.filter(blog=post.blog, name__iexact=name).first()
        if tag is None:
            tag = Tag.objects.create(blog=post.blog, name=name)
        tags.append(tag)
    PostTag.objects.filter(post=post).delete()
    PostTag.objects.bulk_create([PostTag(post=post, tag=tag) for tag in tags])


def publish(blog, data, draft=None):
    """발행. 새 기록이거나, 임시저장한 기록(draft)을 발행한다.

    글 번호는 한채의 last_post_no 를 잠그고 하나 올려 정한다. 호출하는 쪽이 트랜잭션을 연다.
    """
    from apps.blogs.models import Blog

    locked = Blog.objects.select_for_update().get(pk=blog.pk)
    locked.last_post_no += 1
    locked.save(update_fields=["last_post_no", "updated_at"])

    if draft is None:
        post = Post(blog=blog, client_token=data.get("client_token") or None)
        data = {"visibility": Post.Visibility.PUBLIC, **data}
    else:
        post = draft
    post.post_no = locked.last_post_no
    post.status = Post.Status.PUBLISHED
    post.published_at = timezone.now()
    apply_fields(post, data, blog)
    post.save()
    link_images(post, blog.owner)
    post.save(update_fields=["first_image"])
    if draft is None or "tags" in data:
        set_tags(post, data.get("tags", []))
    return post


def save_draft(blog, data, draft=None):
    """임시저장 (POST-11). 번호 · 발행일 없이 DRAFT 로 둔다. 사진도 글에 이어 정리 작업이 지우지 않게 한다."""
    if draft is None:
        draft = Post(blog=blog, status=Post.Status.DRAFT)
        data = {"visibility": Post.Visibility.PUBLIC, "title": "", "content": "", **data}
    apply_fields(draft, data, blog, allow_empty=True)
    draft.save()
    if "content" in data:
        link_images(draft, blog.owner)
        draft.save(update_fields=["first_image"])
    if "tags" in data:
        set_tags(draft, data["tags"])
    return draft


def update(post, data):
    apply_fields(post, data, post.blog)
    post.save()
    if "content" in data:
        link_images(post, post.blog.owner)
        post.save(update_fields=["first_image"])
    if "tags" in data:
        set_tags(post, data["tags"])
    return post
