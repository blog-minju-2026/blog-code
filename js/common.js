/**
 * 여러 화면이 함께 쓰는 도구: 주소 만들기, 날짜, 글자 이스케이프, 헤더 메뉴
 */

// ----- 주소 -----
// 로컬에서는 한채 주소를 ?address= 로 넘긴다.
// 서브도메인({주소}.한채도메인)으로 바꿀 때는 이 묶음만 고치면 된다.
const Links = {
  village: () => '/',
  login: (next) => (next ? `/login?next=${encodeURIComponent(next)}` : '/login'),
  build: () => '/build',
  yard(address, filter = {}) {
    const params = new URLSearchParams({ address });
    Object.entries(filter).forEach(([key, value]) => {
      if (value !== undefined && value !== null) params.set(key, value);
    });
    return `/yard?${params}`;
  },
  post: (address, no) => `/post?address=${encodeURIComponent(address)}&no=${no}`,
  write: (no) => (no ? `/write?no=${no}` : '/write'),
  me: () => '/me',
  admin: (tab, filter = {}) => {
    const params = new URLSearchParams(Object.entries({ tab, ...filter }).filter(([, v]) => v !== undefined && v !== null && v !== ''));
    return params.toString() ? `/admin?${params}` : '/admin';
  },
  settings: () => '/settings',
  managePosts: (filter = {}) => {
    const params = new URLSearchParams(Object.entries(filter).filter(([, v]) => v !== undefined && v !== null && v !== ''));
    return params.toString() ? `/manage-posts?${params}` : '/manage-posts';
  },
  topic: (slug) => `/topic?slug=${encodeURIComponent(slug)}`,
  rooms: () => '/rooms',
  neighbors: () => '/neighbors',
  guestbook: (address, page) => `/guestbook?address=${encodeURIComponent(address)}${page > 1 ? `&page=${page}` : ''}`,
  search(q, { type, sort, page } = {}) {
    const params = new URLSearchParams({ q });
    if (type && type !== 'posts') params.set('type', type);
    if (sort && sort !== 'relevance') params.set('sort', sort);
    if (page > 1) params.set('page', page);
    return `/search?${params}`;
  },
  here: () => location.pathname + location.search,
};

// 같은 사이트 안의 주소면 그 경로를, 아니면 마을('/')을 돌려준다
function safeNext(value) {
  if (!value) return '/';
  try {
    const url = new URL(value, location.origin);
    return url.origin === location.origin ? url.pathname + url.search + url.hash : '/';
  } catch (e) {
    return '/';
  }
}

// 소셜 로그인 버튼을 보일지. 제공사 앱 키를 등록하고 서버의 SOCIAL_LOGIN=1 을 켠 뒤 true 로
const SOCIAL_LOGIN_READY = false;

// ----- 글자 -----
function escapeHTML(text) {
  return String(text ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[ch]);
}

// 방 이름. category 가 null 이면 마루(방 없음)
function roomName(category) {
  return category ? category.name : '마루';
}

// 기록 발행 · 댓글의 중복 요청 막기 토큰 (API 명세서 2.6)
function newClientToken() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    return (c === 'x' ? r : (r % 4) + 8).toString(16);
  });
}

// ----- 날짜 (저장은 UTC, 보여 줄 때 한국 시간) -----
const KST = { timeZone: 'Asia/Seoul' };

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('ko-KR', { ...KST, month: 'long', day: 'numeric' });
}

function formatLongDate(iso) {
  return new Date(iso).toLocaleDateString('ko-KR', { ...KST, year: 'numeric', month: 'long', day: 'numeric' });
}

function formatDateTime(iso) {
  return new Date(iso).toLocaleString('ko-KR', { ...KST, month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}

// 이용 제한 안내 (ADMIN-02). detail: 서버가 SUSPENDED 와 함께 준 { reason, ends_at }
function suspendedMessage({ reason, ends_at: endsAt }) {
  const until = endsAt ? `${formatDateTime(endsAt)}까지` : '기한 없음';
  return `이용이 제한된 계정이에요 (${until}). 사유: ${reason}`;
}

// 방금 · 12분 전 · 3시간 전 · 어제 · 10월 8일
function timeAgo(iso) {
  const minutes = Math.floor((Date.now() - new Date(iso)) / 60000);
  if (minutes < 1) return '방금';
  if (minutes < 60) return `${minutes}분 전`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)}시간 전`;
  if (minutes < 60 * 48) return '어제';
  return formatDate(iso);
}

// ----- 썸네일 -----
// 사진이 있으면 <img>, 없으면 빗금 자리
function thumbHTML(src, className) {
  if (src) return `<img class="${className}" src="${escapeHTML(src)}" alt="">`;
  return `<div class="${className} thumb" aria-hidden="true"></div>`;
}

// ----- 릴리즈 노트 -----
// 내용은 assets/releases.json. 맨 앞이 최신이다
const SEEN_RELEASE_KEY = 'hanchae.seenRelease';
let releasesPromise = null;

function loadReleases() {
  if (!releasesPromise) {
    releasesPromise = fetch('/assets/releases.json', { cache: 'no-cache' })
      .then((res) => {
        if (!res.ok) throw new Error('릴리즈 노트를 불러오지 못했어요.');
        return res.json();
      })
      .then((data) => data.releases || []);
  }
  return releasesPromise;
}

// 이 브라우저에서 본 최신 버전 (저장소를 못 쓰면 없는 것으로)
function seenRelease() {
  try {
    return localStorage.getItem(SEEN_RELEASE_KEY);
  } catch (e) {
    return null;
  }
}

function markReleaseSeen(version) {
  try {
    localStorage.setItem(SEEN_RELEASE_KEY, version);
  } catch (e) {
    // 저장소를 못 쓰면 다음에도 점이 보일 뿐이다
  }
}

// 아직 보지 않은 새 릴리즈가 있으면 헤더의 '릴리즈' 버튼에 점을 단다
async function markNewRelease() {
  const button = document.querySelector('.hc-release');
  if (!button || button.getAttribute('aria-current') === 'page') return;
  try {
    const [latest] = await loadReleases();
    if (latest && latest.version !== seenRelease()) {
      button.classList.add('has-new');
      button.setAttribute('aria-label', `릴리즈 (새 소식 v${latest.version})`);
    }
  } catch (e) {
    // 점을 못 달아도 버튼은 그대로 쓸 수 있다
  }
}

// ----- 마을 목록의 기록 줄 (골목 · 찾기 · 이웃 소식) -----
// titleHTML: 제목을 강조해 넘길 때 (이미 이스케이프한 HTML)
function villagePostRowHTML(p, titleHTML) {
  return `
    <a class="post-row" href="${Links.post(p.blog.address, p.no)}">
      <div class="post-row-text">
        <span class="post-row-title">${titleHTML || escapeHTML(p.title)}</span>
        <span class="post-row-excerpt">${escapeHTML(p.excerpt)}</span>
        <span class="post-row-meta with-house">
          <span class="hyeonpan hyeonpan-sm">${escapeHTML(p.blog.name)}</span>
          ${escapeHTML(roomName(p.category))} · ${timeAgo(p.published_at)} · 공감 ${p.like_count}
        </span>
      </div>
      ${thumbHTML(p.thumbnail_url, 'thumb-img row-thumb')}
    </a>`;
}

// 페이지 번호 (API 명세서 2.5 의 page 결과). link(p) 는 그 페이지 주소
function pagerHTML(result, link) {
  if (result.total_pages <= 1) return '';
  const pages = Array.from({ length: result.total_pages }, (_, i) => i + 1)
    .filter((p) => Math.abs(p - result.page) <= 4 || p === 1 || p === result.total_pages);
  let last = 0;
  const numbers = pages.map((p) => {
    const gap = p - last > 1 ? '<span class="disabled" aria-hidden="true">…</span>' : '';
    last = p;
    return gap + (p === result.page ? `<span aria-current="page">${p}</span>` : `<a href="${link(p)}">${p}</a>`);
  }).join('');
  return (result.page > 1 ? `<a href="${link(result.page - 1)}" aria-label="이전 페이지">‹</a>` : '<span class="disabled" aria-hidden="true">‹</span>')
    + numbers
    + (result.page < result.total_pages ? `<a href="${link(result.page + 1)}" aria-label="다음 페이지">›</a>` : '<span class="disabled" aria-hidden="true">›</span>');
}

// ----- 프로필 사진 -----
// 사진이 있으면 <img>, 없으면 빈 동그라미 (사진은 하나: 내 정보의 프로필 사진이 대문에도 걸린다)
function avatarHTML(url, className = '') {
  return url
    ? `<img class="avatar ${className}" src="${escapeHTML(url)}" alt="">`
    : `<span class="avatar ${className}" aria-hidden="true"></span>`;
}

// ----- 한채 관리 (주인) -----
// 관리 화면 위의 작은 대문
function ownerGateHTML(blog) {
  return `
    <div class="giwa" aria-hidden="true"></div>
    <div class="dancheong-band" aria-hidden="true"></div>
    <div class="gate-inner">
      <a class="hyeonpan" href="${Links.yard(blog.address)}">${escapeHTML(blog.name)}</a>
      <span class="post-gate-meta">${escapeHTML(blog.owner.nickname || '')} · 이웃 ${blog.subscriber_count}</span>
      <div class="gate-actions"><a class="btn btn-secondary" href="${Links.yard(blog.address)}">내 마당 보기</a></div>
    </div>`;
}

// 관리 탭: 한채 관리 · 기록 관리 · 방 관리 · 댓글 · 방명록
function manageTabsHTML(current) {
  const tab = (key, label, href) => (key === current
    ? `<a href="${href}" aria-current="page">${label}</a>`
    : `<a href="${href}">${label}</a>`);
  return `
    ${tab('settings', '한채 관리', Links.settings())}
    ${tab('posts', '기록 관리', Links.managePosts())}
    ${tab('rooms', '방 관리', Links.rooms())}
    <span class="tab-off">댓글 · 방명록 <small>2차</small></span>`;
}

// 주인만 들어오는 화면: 로그인 안 했으면 로그인으로, 한채가 없으면 한채 짓기로. 통과하면 { user, blog }
async function requireOwner() {
  const user = await Auth.currentUser();
  if (!user) {
    location.replace(Links.login(Links.here()));
    return null;
  }
  if (!user.blog_address) {
    location.replace(Links.build());
    return null;
  }
  const blog = await Store.getBlog(user.blog_address);
  return { user, blog };
}

// ----- 확인 창 -----
// 되돌릴 수 없는 동작 앞에서 묻는다. 확인하면 true (시안 · 기록 관리의 '삭제 확인')
function confirmDialog({ title, text, confirmLabel = '확인', danger = false }) {
  return new Promise((resolve) => {
    const dialog = document.createElement('dialog');
    dialog.className = 'hc-dialog';
    dialog.innerHTML = `
      <h2>${escapeHTML(title)}</h2>
      <p>${escapeHTML(text)}</p>
      <div class="hc-dialog-actions">
        <button type="button" class="btn btn-secondary" value="cancel">취소</button>
        <button type="button" class="btn ${danger ? 'btn-danger' : 'btn-primary'}" value="ok">${escapeHTML(confirmLabel)}</button>
      </div>`;
    const close = (ok) => {
      dialog.close();
      dialog.remove();
      resolve(ok);
    };
    dialog.addEventListener('click', (e) => {
      const button = e.target.closest('button');
      if (button) close(button.value === 'ok');
      else if (e.target === dialog) close(false); // 바깥을 누르면 취소
    });
    dialog.addEventListener('cancel', (e) => {
      e.preventDefault();
      close(false);
    });
    document.body.appendChild(dialog);
    dialog.showModal();
    dialog.querySelector('[value="cancel"]').focus();
  });
}

// ----- 헤더 메뉴 -----
// 로그인 전: 로그인 / 로그인 뒤: 내 한채(없으면 한채 짓기) · 글쓰기
// showMe: 오른쪽 끝에 지금 로그인한 나(사진 · 닉네임)를 보인다 (방명록 시안)
async function renderHeaderNav(nav, { showMe = false } = {}) {
  markNewRelease();
  let user;
  try {
    user = await Auth.currentUser();
  } catch (err) {
    // 내 정보를 못 받았어도 누구나 보는 화면은 그대로 연다. 주인만 보는 화면은 그 화면이 다시 물어 오류를 보인다
    console.error(err);
    user = null;
  }
  if (!user) {
    nav.innerHTML = `<a class="btn btn-secondary" href="${Links.login(Links.here())}">로그인</a>`;
    return { user: null };
  }
  nav.innerHTML = user.blog_address
    ? `<a class="plain" href="${Links.yard(user.blog_address)}">내 한채</a>
       <a class="btn btn-primary" href="${Links.write()}">글쓰기</a>`
    : `<a class="btn btn-primary" href="${Links.build()}">한채 짓기</a>`;
  // 서비스 관리자에게만 마을 관리 (ADMIN-01)
  if (user.role === 'ADMIN') nav.insertAdjacentHTML('afterbegin', `<a class="plain" href="${Links.admin()}">마을 관리</a>`);
  if (showMe) {
    nav.insertAdjacentHTML('beforeend', `
      <a class="hc-me" href="${Links.me()}" aria-label="내 정보: ${escapeHTML(user.nickname)}">
        ${avatarHTML(user.profile_image_url)}<span>${escapeHTML(user.nickname)}</span>
      </a>`);
  }
  return { user };
}

// 대문의 이웃 맺기 · 끊기 버튼. 로그인 전이면 로그인으로 보낸다
function bindNeighborButton(button, blog, onCount) {
  let subscribed = blog.is_subscribed;
  const paint = () => {
    button.className = `btn ${subscribed ? 'btn-secondary' : 'btn-primary'}`;
    button.setAttribute('aria-pressed', String(subscribed));
    button.textContent = subscribed ? '이웃이에요' : '이웃 맺기';
  };
  paint();
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      if (!(await Auth.currentUser())) {
        location.href = Links.login(Links.here());
        return;
      }
      const result = await Store.setNeighbor(blog.address, !subscribed);
      subscribed = result.subscribed;
      paint();
      onCount(result.subscriber_count);
    } catch (err) {
      alert(err.message);
    } finally {
      button.disabled = false;
    }
  });
}

// ----- 닫힌 대문: 오류 화면 (SCR-20) -----
// 대문 그림과 '마을로 돌아가기'는 같고, 현판 · 제목 · 설명 · 두 번째 버튼만 경우마다 바뀐다
const LOST_CASES = {
  notFound: { code: '404', eyebrow: '없는 주소', title: '찾는 집이 없어요', text: '주소가 바뀌었거나 허물어진 한채, 지워진 기록이에요. 마을에서 다시 찾아 보세요.', action: 'back' },
  forbidden: { code: '403', eyebrow: '들어갈 수 없는 곳', title: '문이 닫혀 있어요', text: '주인만 들어갈 수 있는 곳이에요. 내 한채라면 로그인한 뒤 다시 열어 주세요.', action: 'login' },
  serverError: { code: '500', eyebrow: '잠시 문제가 생겼어요', title: '대문이 잠시 고장 났어요', text: '서버에 문제가 생겨 화면을 열지 못했어요. 잠시 뒤 다시 들어와 주세요.', action: 'reload' },
  loadFailed: { code: '!', eyebrow: '연결이 끊겼어요', title: '화면을 불러오지 못했어요', text: '인터넷 연결이 끊겼거나 서버가 잠시 답하지 않아요. 연결을 확인하고 다시 불러와 주세요.', action: 'reload' },
  badRequest: { code: '400', eyebrow: '잘못된 요청', title: '열 수 없는 주소예요', text: '주소에 담긴 값이 올바르지 않아요. 이전 화면에서 다시 들어와 주세요.', action: 'back' },
  tooMany: { code: '429', eyebrow: '잠시 쉬어 가요', title: '요청이 너무 잦아요', text: '잠시 뒤 다시 불러와 주세요.', action: 'reload' },
  suspended: { code: '403', eyebrow: '이용 제한', title: '이용이 제한된 계정이에요', text: '이용이 제한되어 로그아웃됐어요.', action: 'back' },
  broken: { code: '!', eyebrow: '잠시 문제가 생겼어요', title: '화면을 열지 못했어요', text: '화면을 그리다 문제가 생겼어요. 다시 불러와도 그대로면 잠시 뒤 다시 들어와 주세요.', action: 'reload' },
};

function lostHTML(kind, { text } = {}) {
  const c = LOST_CASES[kind] || LOST_CASES.notFound;
  const second = {
    back: '<button type="button" class="btn btn-secondary" data-lost="back">이전 화면으로</button>',
    login: `<a class="btn btn-secondary" href="${Links.login(Links.here())}">로그인</a>`,
    reload: '<button type="button" class="btn btn-secondary" data-lost="reload">다시 불러오기</button>',
  }[c.action];
  return `
    <div class="lost-gate" aria-hidden="true">
      <div class="lost-roof"><i class="lost-roof-peak"></i><i class="lost-roof-eaves"></i><i class="lost-roof-tip lost-roof-tip-l"></i><i class="lost-roof-tip lost-roof-tip-r"></i></div>
      <div class="dancheong-band"></div>
      <div class="lost-frame">
        <span class="hyeonpan lost-code">${c.code}</span>
        <div class="lost-doors"><span><i class="lost-ring"></i></span><span><i class="lost-ring"></i></span></div>
      </div>
      <div class="lost-step"></div>
    </div>
    <div class="lost-text">
      <span class="lost-eyebrow">${c.eyebrow}</span>
      <h1>${c.title}</h1>
      <p>${escapeHTML(text || c.text)}</p>
      <div class="lost-actions">
        <a class="btn btn-primary" href="/">마을로 돌아가기</a>
        ${second}
      </div>
    </div>`;
}

// 닫힌 대문의 버튼: 이전 화면 · 다시 불러오기
document.addEventListener('click', (e) => {
  const button = e.target.closest('[data-lost]');
  if (!button) return;
  if (button.dataset.lost === 'reload') location.reload();
  // 다른 사이트에서 바로 들어왔으면 이전 화면이 없으니 마을로
  if (button.dataset.lost === 'back') {
    if (document.referrer.startsWith(location.origin) && history.length > 1) history.back();
    else location.href = '/';
  }
});

// 본문을 숨기고 그 자리에 닫힌 대문을 보여 준다
function showLost(kind, options) {
  document.querySelectorAll('body > main, body > .house, body > .village, body > .gate, body > form').forEach((el) => {
    el.hidden = true;
  });
  const lost = document.createElement('main');
  lost.className = 'lost';
  lost.innerHTML = lostHTML(kind, options);
  document.body.insertBefore(lost, document.querySelector('body > footer'));
  document.title = `${(LOST_CASES[kind] || LOST_CASES.notFound).title} · 한채`;
}

// 다른 화면으로 넘어가는 중에 끊긴 요청은 오류가 아니다
let leavingPage = false;
window.addEventListener('beforeunload', () => { leavingPage = true; });
window.addEventListener('pageshow', () => { leavingPage = false; });

// 화면 시작 함수를 감싸 실패해도 빈 화면으로 멈추지 않게 오류 안내를 보여 준다
function runPage(main) {
  main().catch((err) => {
    if (leavingPage) return;
    console.error(err);
    // 로그인이 끊겼으면(세션 만료) 로그인한 뒤 이 화면으로 돌아오게 한다
    if (err.status === 401) {
      location.replace(Links.login(Links.here()));
      return;
    }
    if (err.code === 'SUSPENDED') {
      showLost('suspended', { text: suspendedMessage(err.detail || {}) });
      return;
    }
    // 서버가 오류로 답했으면 그 종류대로, 답이 없었으면(status 0) '연결 끊김', 서버 오류가 아니면(화면 코드) '문제'
    const kind = { 400: 'badRequest', 403: 'forbidden', 404: 'notFound', 429: 'tooMany' }[err.status]
      || (err.status >= 500 ? 'serverError' : err.status === 0 ? 'loadFailed' : 'broken');
    // 잘못된 값 · 잦은 요청은 서버가 준 문장이 더 정확하다 (예: '찾을 낱말은 50자까지', '12초 뒤에')
    showLost(kind, kind === 'badRequest' || kind === 'tooMany' ? { text: err.firstMessage || err.message } : undefined);
  });
}

// 헤더의 '마을에서 찾기': 찾기 화면으로 간다. 찾기 화면에서는 지금 낱말을 채워 둔다
function bindVillageSearch(form) {
  const input = form.querySelector('input[type="search"]');
  if (location.pathname === '/search') input.value = new URLSearchParams(location.search).get('q') || '';
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) {
      input.focus();
      return;
    }
    location.href = Links.search(q);
  });
}
