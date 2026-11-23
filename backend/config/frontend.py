"""
화면 파일(index.html · css · js · assets)을 Django 가 함께 내보낸다.

화면과 API 를 같은 주소에서 띄워야 세션 쿠키 · CSRF 가 그대로 통한다.
저장소 루트에는 backend/.env 같은 파일도 있으므로, 화면에 필요한 것만 내보낸다.
"""

import logging
import posixpath
import re

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponsePermanentRedirect, JsonResponse
from django.utils.html import escape
from django.views.static import serve

logger = logging.getLogger(__name__)

# 루트의 *.html 과 이 폴더들 안의 파일만 내보낸다
FRONTEND_FOLDERS = {"css", "js", "assets"}


def page_file(name, status):
    """화면 파일 하나를 상태 코드와 함께 돌려준다 (404.html · 500.html). 없으면 글자만."""
    try:
        body = (settings.FRONTEND_DIR / name).read_bytes()
    except OSError:
        body = "찾을 수 없어요." if status == 404 else "잠시 뒤 다시 시도해 주세요."
    return HttpResponse(body, status=status, content_type="text/html; charset=utf-8")


def is_api(request):
    return request.path.startswith("/api/")


def not_found(request, exception=None):
    """없는 주소: 화면은 닫힌 대문(404.html), API 는 명세서 오류 모양(JSON)."""
    if is_api(request):
        return JsonResponse({"error": {"code": "NOT_FOUND", "message": "찾을 수 없어요."}}, status=404, json_dumps_params={"ensure_ascii": False})
    return page_file("404.html", 404)


def bad_request(request, exception=None):
    """받을 수 없는 요청(400): API 는 명세서 오류 모양(JSON)으로. 화면이 서버의 문장을 그대로 보일 수 있게 한다.

    흔한 경우는 보낸 내용이 너무 클 때다 (Django 의 요청 본문 상한 2.5MB. 본문 1MB 상한보다 훨씬 긴 글을 붙여 넣었을 때).
    """
    from django.core.exceptions import RequestDataTooBig
    from django.views import defaults

    if not is_api(request):
        return defaults.bad_request(request, exception)
    message = "보낸 내용이 너무 커요. 나눠서 보내 주세요." if isinstance(exception, RequestDataTooBig) else "요청을 처리할 수 없어요."
    return JsonResponse({"error": {"code": "BAD_REQUEST", "message": message}}, status=400, json_dumps_params={"ensure_ascii": False})


def server_error(request):
    """서버 오류: 화면은 500.html, API 는 JSON. 내부 정보는 담지 않는다."""
    if is_api(request):
        return JsonResponse({"error": {"code": "SERVER_ERROR", "message": "잠시 후 다시 시도해 주세요."}}, status=500, json_dumps_params={"ensure_ascii": False})
    return page_file("500.html", 500)


# ----- 링크 미리보기 (메신저 · SNS 에 주소를 붙였을 때 보이는 제목 · 설명 · 사진) -----
# 화면은 브라우저에서 API 를 불러 그리므로, 주소만 읽어 가는 미리보기 로봇에게는 모든 기록이 '한채 · 기록'으로만 보인다.
# 그래서 기록(/post) · 마당(/yard) 화면을 내보낼 때 <head> 에 그 기록 · 한채의 제목과 og 태그를 채워 준다.
# 누구나 볼 수 있는 것만 채운다 (공개 기록, 열려 있는 한채). 이웃 공개 · 나만 보기 · 숨긴 기록은 화면 파일 그대로 나간다.
PREVIEW_PAGES = {"post.html", "yard.html"}
ADDRESS_RE = re.compile(r"^[a-z0-9-]{4,32}$")


def share_preview(request, path):
    """미리보기에 채울 값 {type, title, heading, description, url, image}. 채울 것이 없으면 None."""
    from apps.common.access import visible_blogs, visible_posts
    from apps.posts.content import media_url

    address = request.GET.get("address", "")
    if not ADDRESS_RE.match(address):
        return None
    blog = visible_blogs().select_related("owner").filter(address=address).first()
    if blog is None:
        return None

    if path == "yard.html":
        owner = blog.owner
        return {
            "type": "website",
            "title": blog.name,
            "heading": f"{blog.name} · 한채",
            "description": blog.description or f"{owner.nickname or ''}의 한채",
            "url": f"/yard?address={address}",
            "image": media_url(owner.profile_image.name) if owner.is_active and owner.profile_image else None,
        }

    no = request.GET.get("no", "")
    if not (no.isascii() and no.isdigit() and len(no) <= 9):
        return None
    post = (
        visible_posts(None)  # 비회원이 볼 수 있는 것: 공개이고 숨기지 않은 발행 기록
        .filter(blog=blog, post_no=int(no))
        .select_related("cover_image", "first_image")
        .first()
    )
    if post is None:
        return None
    image = post.cover_image or post.first_image
    return {
        "type": "article",
        "title": post.title,
        "heading": f"{post.title} · {blog.name}",
        "description": post.excerpt or blog.name,
        "url": f"/post?address={address}&no={post.post_no}",
        # 목록용 작은 사진은 WebP 라 읽지 못하는 미리보기 로봇이 있다. 원본을 건다
        "image": media_url(image.file.name) if image else None,
    }


def page_with_preview(request, path, preview):
    """화면 파일의 <title> 을 바꾸고 </head> 앞에 og 태그를 넣어 돌려준다. 값은 모두 이스케이프한다."""
    html = (settings.FRONTEND_DIR / path).read_text(encoding="utf-8")
    tags = [
        ("name", "description", preview["description"]),
        ("property", "og:site_name", "한채"),
        ("property", "og:type", preview["type"]),
        ("property", "og:title", preview["title"]),
        ("property", "og:description", preview["description"]),
        ("property", "og:url", request.build_absolute_uri(preview["url"])),
        ("name", "twitter:card", "summary_large_image" if preview["image"] and preview["type"] == "article" else "summary"),
    ]
    if preview["image"]:
        tags.append(("property", "og:image", request.build_absolute_uri(preview["image"])))
    meta = "".join(f'  <meta {kind}="{name}" content="{escape(value)}">\n' for kind, name, value in tags)
    # 함수로 바꾼다: 제목에 든 \1 · \g 같은 글자가 바꿀 말의 문법으로 읽히지 않게
    html = re.sub(r"<title>.*?</title>", lambda m: f"<title>{escape(preview['heading'])}</title>", html, count=1, flags=re.S)
    html = html.replace("</head>", meta + "</head>", 1)
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response


def frontend(request, path=""):
    # css/../backend/.env 처럼 폴더 밖으로 나가는 주소를 막는다. 정리한 뒤의 경로로 다시 검사한다
    if "\\" in path or ".." in path.split("/"):
        return not_found(request)
    # /login/ 처럼 끝에 / 가 붙으면 /login 으로 보낸다 (화면의 css/… 같은 상대 주소가 어긋나지 않게)
    if path.endswith("/") and path.strip("/"):
        query = request.META.get("QUERY_STRING", "")
        return HttpResponsePermanentRedirect("/" + path.strip("/") + (f"?{query}" if query else ""))
    path = posixpath.normpath(path).lstrip("/") if path else ""
    if path in ("", "."):
        path = "index.html"
    top, _, rest = path.partition("/")
    if rest:
        allowed = top in FRONTEND_FOLDERS
    else:
        # /login 처럼 확장자 없는 주소는 같은 이름의 .html 화면으로
        if "." not in path and (settings.FRONTEND_DIR / f"{path}.html").is_file():
            path = f"{path}.html"
        allowed = path.endswith(".html")
    if not allowed:
        return not_found(request)
    if path in PREVIEW_PAGES and request.GET.get("address"):
        try:
            preview = share_preview(request, path)
            if preview is not None:
                return page_with_preview(request, path, preview)
        except Exception:
            # 미리보기를 못 채워도 화면은 그대로 연다 (화면이 API 로 다시 묻고, 오류도 거기서 알린다)
            logger.exception("링크 미리보기를 채우지 못했어요")
    try:
        response = serve(request, path, document_root=settings.FRONTEND_DIR)
    except Http404:
        return not_found(request)
    # 화면 파일은 쓸 때마다 서버에 바뀌었는지 묻게 한다 (안 바뀌었으면 304 로 짧게 답한다).
    # 이 줄이 없으면 브라우저가 어림으로 한동안 묵혀 써서, 배포 뒤 새 HTML 과 옛 js · css 가 섞인다
    response["Cache-Control"] = "no-cache"
    return response
