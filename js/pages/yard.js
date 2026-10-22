/**
 * 마당 (SCR-06) · 방 (SCR-07) · 태그별 기록 (SCR-08) · 이 한채에서 찾기 (SCR-21)
 * yard?address=minju                모든 기록
 * yard?address=minju&category=3      한 방의 기록 (category=none 이면 마루)
 * yard?address=minju&tag=Django      한 태그의 기록
 * yard?address=minju&q=쿠키           이 한채에서 찾기
 */
const params = new URLSearchParams(location.search);
const address = params.get('address') || '';
// 거르는 값은 하나만 쓴다 (API 명세서 4.3)
const filter = {
  category: params.get('category') || undefined,
  tag: params.get('tag') || undefined,
  q: (params.get('q') || '').trim() || undefined,
};
const page = Number(params.get('page')) || 1;
const isFiltered = Boolean(filter.category || filter.tag || filter.q);

function postRowHTML(post) {
  const VISIBILITY_MARKS = { PRIVATE: '나만 보기', SUBSCRIBERS: '이웃 공개' };
  const lock = VISIBILITY_MARKS[post.visibility] ? `<span class="private-mark">${VISIBILITY_MARKS[post.visibility]}</span> · ` : '';
  return `
    <a class="post-row" href="${Links.post(post.blog.address, post.no)}">
      <div class="post-row-text">
        <span class="room-label">${escapeHTML(roomName(post.category))}</span>
        <span class="post-row-title">${escapeHTML(post.title)}</span>
        <span class="post-row-excerpt">${escapeHTML(post.excerpt)}</span>
        <span class="post-row-meta">${lock}${formatDate(post.published_at)} · 공감 ${post.like_count} · 댓글 ${post.comment_count}</span>
      </div>
      ${post.thumbnail_url ? thumbHTML(post.thumbnail_url, 'thumb-img') : ''}
    </a>`;
}

// 지금 거르는 조건에 맞는 제목 · 위치
function describeFilter(blog, rooms) {
  if (filter.category) {
    const room = rooms.rooms.find((r) => String(r.id) === filter.category);
    const name = filter.category === 'none' ? '마루' : (room ? room.name : '없는 방');
    return { title: name, sub: '이 방에 쌓인 기록', crumb: name };
  }
  if (filter.tag) return { title: `#${filter.tag}`, sub: '이 태그가 붙은 기록', crumb: `#${filter.tag}` };
  if (filter.q) return { title: `‘${filter.q}’ 찾은 결과`, sub: `${blog.name}에서 찾기`, crumb: '찾기' };
  return { title: '마당', sub: '모든 방에서 쌓인 최근 기록', crumb: null };
}

function renderGate(blog, total) {
  document.title = `${blog.name} · 한채`;
  document.getElementById('blog-name').textContent = blog.name;
  document.getElementById('owner-name').textContent = blog.owner.nickname || '떠난 사람';
  document.getElementById('owner-intro').textContent = blog.description || '';
  document.getElementById('owner-photo').innerHTML = avatarHTML(blog.profile_image_url, 'owner-avatar');
  document.getElementById('stats').innerHTML = `이웃 <strong id="neighbor-count">${blog.subscriber_count}</strong> · 기록 <strong>${total}</strong>`;

  const actions = document.getElementById('gate-actions');
  // 주인에게는 이웃 맺기 대신 '글쓰기 · 한채 관리' (기능명세서 5.4)
  actions.innerHTML = blog.is_owner
    ? `<a class="btn btn-primary" href="${Links.write()}">글쓰기</a>
       <a class="btn btn-secondary" href="${Links.settings()}">한채 관리</a>`
    : '<button type="button" class="btn" id="neighbor-button"></button>';
  actions.insertAdjacentHTML('beforeend', `<a class="btn btn-secondary" href="${Links.guestbook(blog.address)}">방명록</a>`);
  if (!blog.is_owner) {
    bindNeighborButton(document.getElementById('neighbor-button'), blog, (count) => {
      document.getElementById('neighbor-count').textContent = count;
    });
  }
}

function renderRooms(rooms) {
  const item = (label, count, href, current) => `
    <li><a href="${href}"${current ? ' aria-current="page"' : ''}>
      <span class="name">${escapeHTML(label)}</span><span class="count">${count}</span>
    </a></li>`;
  const list = [
    item('모든 기록', rooms.total_count, Links.yard(address), !isFiltered),
    ...rooms.rooms.map((r) => item(r.name, r.post_count, Links.yard(address, { category: r.id }), filter.category === String(r.id))),
  ];
  // 마루는 기록이 있을 때만 (API 명세서 4.4)
  if (rooms.uncategorized_count) {
    list.push(item('마루', rooms.uncategorized_count, Links.yard(address, { category: 'none' }), filter.category === 'none'));
  }
  document.getElementById('room-list').innerHTML = list.join('');
}

function renderTags(tags) {
  document.getElementById('tag-list').innerHTML = tags.length
    ? tags.map((t) => `<a class="tag" href="${Links.yard(address, { tag: t.name })}"${filter.tag === t.name ? ' aria-current="page"' : ''}>#${escapeHTML(t.name)}</a>`).join('')
    : '<span class="post-row-meta">아직 태그가 없어요.</span>';
}

function renderList(result, isOwner) {
  const list = document.getElementById('post-list');
  if (!result.items.length) {
    list.innerHTML = `
      <div class="empty">
        <span>${isFiltered ? '맞는 기록이 없어요.' : '아직 마당이 비어 있어요.'}</span>
        ${isOwner && !isFiltered ? `<a class="btn btn-primary" href="${Links.write()}">첫 기록 쓰기</a>` : ''}
      </div>`;
    return;
  }
  list.innerHTML = result.items.map(postRowHTML).join('');
}

function renderPager(result) {
  const pager = document.getElementById('pager');
  if (result.total_pages <= 1) {
    pager.hidden = true;
    return;
  }
  const link = (p) => Links.yard(address, { ...filter, page: p });
  const prev = result.page > 1
    ? `<a href="${link(result.page - 1)}" aria-label="이전 페이지">‹</a>`
    : '<span class="disabled" aria-hidden="true">‹</span>';
  const next = result.page < result.total_pages
    ? `<a href="${link(result.page + 1)}" aria-label="다음 페이지">›</a>`
    : '<span class="disabled" aria-hidden="true">›</span>';
  const numbers = Array.from({ length: result.total_pages }, (_, i) => i + 1)
    .map((p) => (p === result.page ? `<span aria-current="page">${p}</span>` : `<a href="${link(p)}">${p}</a>`))
    .join('');
  pager.innerHTML = prev + numbers + next;
}

async function main() {
  bindVillageSearch(document.getElementById('village-search'));
  await renderHeaderNav(document.getElementById('header-nav'));

  const blog = await Store.getBlog(address);
  if (!blog) {
    showLost('notFound');
    return;
  }

  const [rooms, tags, result] = await Promise.all([
    Store.getRooms(address),
    Store.getTags(address),
    Store.listPosts(address, { ...filter, page }),
  ]);

  renderGate(blog, rooms.total_count);
  renderRooms(rooms);
  renderTags(tags);

  const view = describeFilter(blog, rooms);
  document.getElementById('list-title').textContent = view.title;
  document.getElementById('list-sub').textContent = view.sub;
  document.getElementById('breadcrumb').innerHTML = view.crumb
    ? `<a href="/">마을</a><span aria-hidden="true">›</span><a href="${Links.yard(address)}">${escapeHTML(blog.name)}</a><span aria-hidden="true">›</span><span aria-current="page">${escapeHTML(view.crumb)}</span>`
    : `<a href="/">마을</a><span aria-hidden="true">›</span><span aria-current="page">${escapeHTML(blog.name)}</span>`;

  renderList(result, blog.is_owner);
  renderPager(result);

  const search = document.getElementById('blog-search');
  search.elements.q.value = filter.q || '';
  search.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = search.elements.q.value.trim();
    location.href = q ? Links.yard(address, { q }) : Links.yard(address);
  });

  document.getElementById('gate').hidden = false;
  document.getElementById('house').hidden = false;
}

runPage(main);
