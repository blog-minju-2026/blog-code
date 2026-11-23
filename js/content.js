/**
 * 글 본문(HTML) 처리 도구
 *
 * 에디터로 쓴 본문은 HTML 문자열로 저장된다.
 * 그대로 innerHTML에 넣으면 <script>나 onerror 같은 코드가 실행될 수 있으므로
 * 허용한 태그와 속성만 남기고 나머지는 지운 뒤 화면에 넣는다.
 */

// 허용하는 태그와, 태그별로 허용하는 속성
const ALLOWED_TAGS = {
  p: [], br: [], div: [], span: [],
  h2: [], h3: [], h4: [],
  strong: [], b: [], em: [], i: [], u: [], s: [], strike: [],
  ul: [], ol: [], li: [],
  blockquote: [], pre: [], code: [], hr: [],
  a: ['href'],
  img: ['src', 'alt'],
};

// 태그째로(안의 내용까지) 지울 것들
const REMOVE_WITH_CONTENT = ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'textarea', 'select', 'noscript', 'template'];

// style 속성 중 남길 것
const ALLOWED_STYLES = ['color', 'background-color', 'text-align'];

function isSafeLink(url) {
  // http(s), mailto, 또는 같은 사이트 안의 상대 경로만 허용.
  // 브라우저는 주소 안의 탭 · 줄바꿈 · 앞쪽 제어 문자를 빼고 읽는다 ('java\tscript:' 도 javascript: 다). 같은 눈으로 본다
  const seen = String(url).replace(/[\u0000-\u0020]+/g, '');
  return /^(https?:|mailto:)/i.test(seen) || !/^[a-z][a-z0-9+.-]*:/i.test(seen);
}

// 우리 서버에 올린 사진(/media/...)만. 다른 사이트 사진은 읽는 사람의 접속 정보를 흘린다
function isSafeImage(url) {
  try {
    const parsed = new URL(url, location.origin);
    return parsed.origin === location.origin && parsed.pathname.startsWith('/media/');
  } catch (e) {
    return false;
  }
}

function cleanAttributes(el, tag) {
  Array.from(el.attributes).forEach((attr) => {
    const name = attr.name.toLowerCase();
    const value = attr.value.trim();

    if (name === 'style') {
      const kept = ALLOWED_STYLES
        .map((prop) => {
          const v = el.style.getPropertyValue(prop);
          return v ? `${prop}: ${v};` : '';
        })
        .join(' ')
        .trim();
      if (kept) el.setAttribute('style', kept);
      else el.removeAttribute('style');
      return;
    }

    const allowed = ALLOWED_TAGS[tag].includes(name);
    const safe = (name === 'href' && isSafeLink(value))
      || (name === 'src' && isSafeImage(value))
      || (name === 'alt');

    if (!allowed || !safe) el.removeAttribute(attr.name);
  });

  if (tag === 'a') {
    el.setAttribute('target', '_blank');
    el.setAttribute('rel', 'noopener noreferrer');
  }
}

function cleanChildren(parent) {
  Array.from(parent.childNodes).forEach((node) => {
    if (node.nodeType === Node.TEXT_NODE) return;

    if (node.nodeType !== Node.ELEMENT_NODE) {
      node.remove(); // 주석 등
      return;
    }

    const tag = node.tagName.toLowerCase();

    if (REMOVE_WITH_CONTENT.includes(tag)) {
      node.remove();
      return;
    }

    cleanChildren(node);

    if (!ALLOWED_TAGS[tag]) {
      // 허용하지 않은 태그는 껍데기만 벗기고 안의 내용은 살린다
      node.replaceWith(...node.childNodes);
      return;
    }

    cleanAttributes(node, tag);
  });
}

function sanitizeHTML(html) {
  // DOMParser로 만든 문서는 화면에 붙지 않아서 스크립트가 실행되지 않는다
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html');
  cleanChildren(doc.body);
  return doc.body.innerHTML;
}

// 글 목록의 요약문처럼 태그 없이 글자만 필요할 때
function htmlToText(html) {
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html');
  return (doc.body.textContent || '').replace(/\s+/g, ' ').trim();
}

// 본문의 첫 번째 이미지 주소 (썸네일용)
function findFirstImage(html) {
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html');
  const img = doc.querySelector('img');
  return img ? img.getAttribute('src') : '';
}
