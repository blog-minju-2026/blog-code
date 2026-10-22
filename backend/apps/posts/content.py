"""기록 본문 정제 (API 명세서 4.3, 7.2 '본문 HTML 허용 태그').

에디터가 보낸 HTML 에서 허용한 태그 · 속성만 남긴다. 스크립트 · 이벤트 속성 · 위험한 주소는 모두 지운다.
사진은 우리 서버에 올린 것(/media/...)만 남긴다. 다른 사이트 사진을 걸면 방문자 정보가 새기 때문이다.
"""

import html
import re
from urllib.parse import unquote, urlparse

import nh3
from django.conf import settings
from django.http.request import validate_host

ALLOWED_TAGS = {
    "p", "br", "div", "span", "h2", "h3",
    "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li", "blockquote", "pre", "code", "hr",
    "a", "img",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href"},
    "img": {"src", "alt"},
    "p": {"style"}, "span": {"style"}, "div": {"style"}, "h2": {"style"}, "h3": {"style"}, "li": {"style"},
}
# 글자색 · 정렬만 남긴다
ALLOWED_STYLES = {"color", "background-color", "text-align"}
EXCERPT_LENGTH = 150


def _media_path(url):
    """우리 서버에 올린 파일이면 MEDIA_URL 뒤의 경로(images/2026/10/a.png), 아니면 None.

    주소에 호스트가 붙어 있으면 우리 서비스의 호스트(ALLOWED_HOSTS)일 때만 인정한다.
    경로만 /media/ 로 맞춘 다른 사이트 주소(https://evil.com/media/x.gif)를 막기 위해서다.
    """
    parsed = urlparse(url)
    if parsed.netloc and not validate_host(parsed.hostname or "", settings.ALLOWED_HOSTS):
        return None
    prefix = "/" + settings.MEDIA_URL.lstrip("/")
    if not parsed.path.startswith(prefix):
        return None
    path = parsed.path[len(prefix):]
    # /media/../api/... 처럼 MEDIA 밖을 가리키면 브라우저가 다른 주소로 읽는다 (%2e%2e 도 브라우저에는 .. 다)
    decoded = unquote(path)
    if not path or "\\" in decoded or any(part in ("", ".", "..") for part in decoded.split("/")):
        return None
    return path


def media_url(path):
    """저장 경로 → 화면에 넣는 주소. 호스트 없이 /media/... 로 두어 도메인 · http(s)가 바뀌어도 깨지지 않게 한다."""
    return "/" + settings.MEDIA_URL.lstrip("/") + path


def _filter_attribute(tag, attr, value):
    if tag == "img" and attr == "src":
        path = _media_path(value)
        return media_url(path) if path is not None else None
    return value


def sanitize(content):
    cleaned = nh3.clean(
        content or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        attribute_filter=_filter_attribute,
        filter_style_properties=ALLOWED_STYLES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer nofollow",
    )
    # src 를 잃은 사진은 빈 껍데기라 지운다
    return re.sub(r"<img(?![^>]*\ssrc=)[^>]*>", "", cleaned)


def to_text(content):
    """서식을 뺀 글자 (검색 · 요약용)."""
    text = re.sub(r"<(br|/p|/h2|/h3|/li|/blockquote|/pre|/div)\b[^>]*>", " ", content, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def excerpt(text):
    return text[:EXCERPT_LENGTH]


def image_paths(content):
    """본문에 들어 있는 우리 서버 사진의 경로들 (나온 순서대로)."""
    paths = []
    for src in re.findall(r"<img[^>]*\ssrc=\"([^\"]+)\"", content):
        path = _media_path(html.unescape(src))
        if path and path not in paths:
            paths.append(path)
    return paths
