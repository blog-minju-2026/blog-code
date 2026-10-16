/**
 * 마을 (SCR-01)
 * - 로그인 상태에 따라 헤더 메뉴, 내 자리, 이웃 소식을 바꾼다.
 * - 골목 · 새 기록 · 이웃 소식은 서버에서 받아 온다 (API 명세서 4.9, 4.7).
 * - 지금 많이 읽는 기록 · 북적이는 한채는 순위 API(매 정각 계산)가 생기면 채운다.
 */
const seat = document.getElementById('seat');
const neighbors = document.getElementById('neighbors');
const topicList = document.getElementById('topic-list');
const alleyPosts = document.getElementById('alley-posts');
const FRESH_STEP = 8;
let freshCursor = null;

// ----- 내 자리 -----
function renderSeat(user, myBlog) {
  if (!user) {
    const login = Links.login();
    seat.innerHTML = `
      <h2>마을에 들어오세요</h2>
      <p class="seat-desc">로그인하면 내 한채를 짓고, 이웃을 맺고, 기록에 공감을 남길 수 있어요.</p>
      <a class="btn btn-primary btn-block" href="${login}">로그인</a>
      ${SOCIAL_LOGIN_READY ? `<div class="social">
        <a class="btn btn-secondary" href="/accounts/kakao/login/?next=/">카카오</a>
        <a class="btn btn-secondary" href="/accounts/google/login/?next=/">구글</a>
        <a class="btn btn-secondary" href="/accounts/naver/login/?next=/">네이버</a>
      </div>` : ''}
      <p class="seat-join">처음이신가요? <a class="text-link" href="/login?tab=signup">이메일로 가입하기</a></p>`;
    neighbors.hidden = true;
    return;
  }

  const nickname = escapeHTML(user.nickname);
  const home = myBlog
    ? `<a class="text-link" href="${Links.yard(myBlog.address)}">${escapeHTML(myBlog.name)} · 이웃 ${myBlog.subscriber_count}</a>`
    : '<span class="seat-desc">아직 지은 한채가 없어요</span>';
  const actions = myBlog
    ? `<a class="btn btn-secondary" href="${Links.yard(myBlog.address)}">내 한채</a>
       <a class="btn btn-primary" href="${Links.write()}">글쓰기</a>`
    : `<a class="btn btn-primary me-build" href="${Links.build()}">한채 짓기</a>`;
  seat.innerHTML = `
    <div class="me">
      ${avatarHTML(user.profile_image_url, 'me-avatar')}
      <div class="me-info">
        <h2>${nickname}</h2>
        ${home}
      </div>
    </div>
    <div class="me-actions">${actions}</div>
    <div class="me-links">
      <a class="text-link" href="${Links.me()}">내 정보</a>
      <button type="button" id="logout-button">로그아웃</button>
    </div>`;
  neighbors.hidden = false;

  document.getElementById('logout-button').addEventListener('click', async () => {
    try {
      await Auth.logOut();
      location.reload();
    } catch (err) {
      alert(err.message);
    }
  });
}

// ----- 골목 -----
function alleyCardHTML(post) {
  return `
    <a class="alley-card card" href="${Links.post(post.blog.address, post.no)}">
      ${thumbHTML(post.thumbnail_url, 'thumb-img alley-thumb')}
      <span class="alley-text">
        <span class="alley-title">${escapeHTML(post.title)}</span>
        <span class="alley-excerpt">${escapeHTML(post.excerpt)}</span>
        <span class="alley-blog">${escapeHTML(post.blog.name)}</span>
      </span>
    </a>`;
}

async function selectTopic(button) {
  topicList.querySelectorAll('button').forEach((b) => {
    b.setAttribute('aria-pressed', String(b === button));
  });
  // '이 골목 더 보기'는 고른 골목의 화면으로
  document.getElementById('alley-more').href = Links.topic(button.dataset.slug);
  const { items: posts } = await Store.topicPosts(button.dataset.slug, { limit: 6 });
  alleyPosts.innerHTML = posts.length
    ? posts.map(alleyCardHTML).join('')
    : `<p class="empty">${escapeHTML(button.textContent)} 골목에는 아직 기록이 없어요.</p>`;
}

async function loadTopics() {
  try {
    const topics = await Store.getTopics();
    topicList.innerHTML = topics
      .map((t) => `<button type="button" data-slug="${escapeHTML(t.slug)}" aria-pressed="false">${escapeHTML(t.name)}</button>`)
      .join('');
    const first = topicList.querySelector('button');
    if (first) await selectTopic(first);
  } catch (err) {
    topicList.innerHTML = '<p class="empty">골목을 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.</p>';
  }
}

topicList.addEventListener('click', (e) => {
  const button = e.target.closest('button');
  if (button) selectTopic(button);
});


// ----- 이웃 소식 -----
async function renderNeighborPosts() {
  const { items: posts } = await Store.neighborFeed({ limit: 3 });
  document.getElementById('neighbor-posts').innerHTML = posts.length
    ? posts.map((p) => `
        <a class="neighbor-card" href="${Links.post(p.blog.address, p.no)}">
          <span class="neighbor-meta">${escapeHTML(p.blog.name)} · ${timeAgo(p.published_at)}</span>
          <span class="neighbor-title">${escapeHTML(p.title)}</span>
        </a>`).join('')
    : '<p class="empty">이웃을 맺으면 이웃 한채의 새 기록이 여기에 보여요.</p>';
}

// ----- 새 기록 (커서로 더 불러오기) -----
function freshRowHTML(p) {
  return `
    <a class="post-row" href="${Links.post(p.blog.address, p.no)}">
      <div class="post-row-text">
        <span class="post-row-title">${escapeHTML(p.title)}</span>
        <span class="post-row-excerpt">${escapeHTML(p.excerpt)}</span>
        <span class="post-row-meta">${escapeHTML(p.blog.name)} · ${escapeHTML(roomName(p.category))} · ${timeAgo(p.published_at)}</span>
      </div>
      ${thumbHTML(p.thumbnail_url, 'thumb-img fresh-thumb')}
    </a>`;
}

async function loadFresh() {
  const box = document.getElementById('fresh-posts');
  const { items, next_cursor: next } = await Store.newPosts({ cursor: freshCursor, limit: FRESH_STEP });
  const more = document.getElementById('fresh-more');
  if (more) more.remove();
  if (!freshCursor && !items.length) {
    box.innerHTML = '<p class="empty">아직 마을에 쌓인 기록이 없어요. 첫 기록을 남겨 보세요.</p>';
    return;
  }
  box.insertAdjacentHTML('beforeend', items.map(freshRowHTML).join(''));
  freshCursor = next;
  if (next) {
    box.insertAdjacentHTML('beforeend', '<button type="button" class="btn btn-secondary fresh-more" id="fresh-more">새 기록 더 불러오기</button>');
    document.getElementById('fresh-more').addEventListener('click', loadFresh);
  }
}

// ----- 사이드바: 순위 · 북적이는 한채 (매 정각 기준) -----
// "14시 기준 · 최근 1시간" (기능명세서 9.2). 조회가 없으면 기준을 비운다
function basisLabel(ranking) {
  if (ranking.basis === 'EMPTY') return '';
  const hour = new Date(ranking.window_end).getHours();
  return `${hour}시 기준 · 최근 ${ranking.basis === '1H' ? '1시간' : '24시간'}`;
}

async function renderRankings() {
  const [posts, blogs] = await Promise.all([Store.postRanking(10), Store.blogRanking(4)]);
  document.getElementById('rank-basis').textContent = basisLabel(posts);
  document.getElementById('rank-list').innerHTML = posts.items.length
    ? posts.items.map((r) => `
      <li>
        <a href="${Links.post(r.post.blog.address, r.post.no)}">
          <span class="rank-no">${r.position}</span>
          <span class="rank-text">
            <span class="rank-title">${escapeHTML(r.post.title)}</span>
            <span class="rank-blog">${escapeHTML(r.post.blog.name)}</span>
          </span>
        </a>
      </li>`).join('')
    : '<li class="empty">아직 읽힌 기록이 없어요. 매 정각에 다시 세요.</li>';

  document.getElementById('house-basis').textContent = basisLabel(blogs);
  document.getElementById('house-list').innerHTML = blogs.items.length
    ? blogs.items.map((r) => `
      <a class="house-row" href="${Links.yard(r.blog.address)}">
        <span class="hyeonpan">${escapeHTML(r.blog.name)}</span>
        <span class="house-text">
          <span class="house-meta">${escapeHTML(r.blog.owner.nickname || '떠난 사람')} · 이웃 ${r.blog.subscriber_count}</span>
          ${r.top_post ? `<span class="house-top">${escapeHTML(r.top_post.title)}</span>` : ''}
        </span>
      </a>`).join('')
    : '<p class="empty">아직 북적이는 한채가 없어요. 매 정각에 다시 세요.</p>';
}

async function main() {
  bindVillageSearch(document.getElementById('village-search'));
  const { user } = await renderHeaderNav(document.getElementById('header-nav'));
  const myBlog = user ? await Store.getMyBlog() : null;
  renderSeat(user, myBlog);

  // 한채가 있으면 어귀의 한채 짓기 버튼을 내 한채로
  if (myBlog) {
    const build = document.querySelector('.entry-actions .btn');
    build.textContent = '내 한채 가기';
    build.href = Links.yard(myBlog.address);
  }

  await Promise.all([
    loadTopics(),
    user ? renderNeighborPosts() : null,
    loadFresh(),
    renderRankings().catch(() => {
      document.getElementById('rank-list').innerHTML = '<li class="empty">순위를 불러오지 못했어요.</li>';
    }),
  ]);
}

runPage(main);
