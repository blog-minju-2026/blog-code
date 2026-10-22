/**
 * 기록 관리 (SCR-15) /manage-posts
 * manage-posts                       모든 기록 (나만 보기 포함)
 * manage-posts?visibility=PRIVATE     공개 범위로 거르기 (PUBLIC · SUBSCRIBERS · PRIVATE)
 * manage-posts?status=draft          임시저장한 기록 (이어 쓰기 · 지우기)
 * 목록에서 공개 범위를 바로 바꾸고, 수정 · 삭제한다.
 */
const params = new URLSearchParams(location.search);
const VISIBILITIES = [
  { value: 'PUBLIC', label: '공개' },
  { value: 'SUBSCRIBERS', label: '이웃 공개' },
  { value: 'PRIVATE', label: '나만 보기' },
];
const visibility = VISIBILITIES.some((v) => v.value === params.get('visibility')) ? params.get('visibility') : '';
const draftMode = params.get('status') === 'draft';
const page = Number(params.get('page')) || 1;
const FILTERS = [{ value: '', label: '전체' }, ...VISIBILITIES];
let address = '';

// 전체 · 공개 범위마다 개수 (주인은 목록에 이웃 공개 · 나만 보기도 섞여 온다)
async function loadCounts() {
  const [drafts, ...results] = await Promise.all([
    Store.listDrafts(address, { size: 1 }),
    ...FILTERS.map((f) => Store.listPosts(address, { visibility: f.value, size: 1 })),
  ]);
  const counts = Object.fromEntries(FILTERS.map((f, i) => [f.value, results[i].total]));
  document.getElementById('counts').innerHTML = `기록 <strong>${counts['']}</strong> · `
    + VISIBILITIES.map((v) => `${v.label} <strong>${counts[v.value]}</strong>`).join(' · ')
    + ` · 임시저장 <strong>${drafts.total}</strong>`;
  document.getElementById('filters').innerHTML = FILTERS
    .map((f) => `<a href="${Links.managePosts({ visibility: f.value })}"${!draftMode && f.value === visibility ? ' aria-current="page"' : ''}>${f.label} ${counts[f.value]}</a>`)
    .join('')
    + `<a href="${Links.managePosts({ status: 'draft' })}"${draftMode ? ' aria-current="page"' : ''}>임시저장 ${drafts.total}</a>`;
}

// ----- 임시저장 목록 -----
function draftRowHTML(d) {
  const title = d.title ? escapeHTML(d.title) : '<span class="draft-untitled">제목 없음</span>';
  const parts = [escapeHTML(roomName(d.category)), d.image_count ? `사진 ${d.image_count}장` : '사진 없음', `본문 ${d.content_length}자`];
  return `
    <div class="manage-row draft-row" data-draft="${d.id}">
      <div class="manage-post-text">
        <a class="manage-post-title" href="${Links.writeDraft(d.id)}">${title}</a>
        <span class="manage-post-meta">${parts.join(' · ')}</span>
      </div>
      <span class="manage-date">${formatDateTime(d.updated_at)}</span>
      <span class="manage-tools">
        <a class="text-link" href="${Links.writeDraft(d.id)}">이어 쓰기</a>
        <button type="button" class="text-link delete" data-delete-draft="${d.id}" data-title="${escapeHTML(d.title || '제목 없음')}">삭제</button>
      </span>
    </div>`;
}

async function loadDrafts() {
  const result = await Store.listDrafts(address, { page });
  document.getElementById('rows').innerHTML = result.items.length
    ? result.items.map(draftRowHTML).join('')
    : `
      <div class="manage-empty">
        <strong>임시저장한 기록이 없어요</strong>
        <span>글쓰기에서 '임시저장'을 누르면 발행하지 않고 여기에 남겨 둬요. 나만 볼 수 있어요.</span>
        <a class="btn btn-secondary" href="${Links.write()}">새 기록 쓰기</a>
      </div>`;
  const pager = document.getElementById('pager');
  pager.hidden = result.total_pages <= 1;
  if (!pager.hidden) pager.innerHTML = pagerHTML(result, (p) => Links.managePosts({ status: 'draft', page: p }));
}

function rowHTML(p) {
  const topic = p.topic ? `골목 ${escapeHTML(p.topic.name)}` : '골목 없음';
  // 관리자가 숨긴 기록은 공개 범위와 상관없이 다른 사람에게 보이지 않는다 (ADMIN-03)
  const hidden = p.hidden ? `<span class="private-mark" title="사유: ${escapeHTML(p.hidden.reason)}">관리자가 숨김 · ${escapeHTML(p.hidden.reason)}</span>` : '';
  return `
    <div class="manage-row" data-no="${p.no}">
      <div class="manage-post">
        ${thumbHTML(p.thumbnail_url, 'thumb-img')}
        <div class="manage-post-text">
          <a class="manage-post-title" href="${Links.post(address, p.no)}">${escapeHTML(p.title)}</a>
          <span class="manage-post-meta"><span class="room-label">${escapeHTML(roomName(p.category))}</span>${topic} · 댓글 ${p.comment_count}${hidden}</span>
        </div>
      </div>
      <span class="manage-date">${formatDate(p.published_at)}</span>
      <span class="num stat">${p.view_count} · ${p.like_count}</span>
      <div class="visibility-switch" role="radiogroup" aria-label="‘${escapeHTML(p.title)}’ 공개 범위">
        ${VISIBILITIES.map((v) => `<button type="button" role="radio" data-visibility="${v.value}" aria-checked="${p.visibility === v.value}">${v.label}</button>`).join('')}
      </div>
      <span class="manage-tools">
        <a class="text-link" href="${Links.write(p.no)}">수정</a>
        <button type="button" class="text-link delete" data-delete="${p.no}" data-title="${escapeHTML(p.title)}">삭제</button>
      </span>
    </div>`;
}

function emptyHTML() {
  const label = FILTERS.find((f) => f.value === visibility).label;
  return `
    <div class="manage-empty">
      <strong>${visibility ? `${label} 기록이 없어요` : '아직 쌓인 기록이 없어요'}</strong>
      <span>${visibility ? '거르는 조건에 맞는 기록이 없어요.' : '첫 기록을 남겨 보세요.'}</span>
      <a class="btn btn-secondary" href="${Links.write()}">새 기록 쓰기</a>
    </div>`;
}

function renderPager(result) {
  const pager = document.getElementById('pager');
  if (result.total_pages <= 1) {
    pager.hidden = true;
    return;
  }
  pager.innerHTML = pagerHTML(result, (p) => Links.managePosts({ visibility, page: p }));
}

async function loadRows() {
  const result = await Store.listPosts(address, { visibility, page });
  document.getElementById('rows').innerHTML = result.items.length ? result.items.map(rowHTML).join('') : emptyHTML();
  renderPager(result);
}

// 공개 범위 바꾸기 · 삭제
document.getElementById('rows').addEventListener('click', async (e) => {
  const switchButton = e.target.closest('[data-visibility]');
  if (switchButton && switchButton.getAttribute('aria-checked') !== 'true') {
    const row = switchButton.closest('[data-no]');
    const buttons = row.querySelectorAll('[data-visibility]');
    buttons.forEach((b) => { b.disabled = true; });
    try {
      await Store.savePost(address, { visibility: switchButton.dataset.visibility }, Number(row.dataset.no));
      buttons.forEach((b) => b.setAttribute('aria-checked', String(b === switchButton)));
      await loadCounts();
      // 거르는 중이면 조건에서 벗어난 기록은 목록에서 빠진다
      if (visibility) await loadRows();
    } catch (err) {
      alert(err.firstMessage || err.message);
    } finally {
      buttons.forEach((b) => { b.disabled = false; });
    }
    return;
  }

  const draftDelete = e.target.closest('[data-delete-draft]');
  if (draftDelete) {
    const ok = await confirmDialog({
      title: '이 임시저장을 지울까요?',
      text: `‘${draftDelete.dataset.title}’을(를) 지우면 되돌릴 수 없어요.`,
      confirmLabel: '삭제',
      danger: true,
    });
    if (!ok) return;
    try {
      await Store.deleteDraft(address, Number(draftDelete.dataset.deleteDraft));
      await Promise.all([loadCounts(), loadDrafts()]);
    } catch (err) {
      alert(err.firstMessage || err.message);
    }
    return;
  }

  const deleteButton = e.target.closest('[data-delete]');
  if (!deleteButton) return;
  const ok = await confirmDialog({
    title: '이 기록을 삭제할까요?',
    text: `‘${deleteButton.dataset.title}’의 댓글과 공감도 함께 사라지고, 되돌릴 수 없어요.`,
    confirmLabel: '삭제',
    danger: true,
  });
  if (!ok) return;
  try {
    await Store.deletePost(address, Number(deleteButton.dataset.delete));
    await Promise.all([loadCounts(), loadRows()]);
  } catch (err) {
    alert(err.firstMessage || err.message);
  }
});

async function main() {
  bindVillageSearch(document.getElementById('village-search'));
  const owner = await requireOwner();
  if (!owner) return;
  const { blog } = owner;
  address = blog.address;
  await renderHeaderNav(document.getElementById('header-nav'));

  document.getElementById('gate').innerHTML = ownerGateHTML(blog);
  document.getElementById('breadcrumb').innerHTML = `
    <a href="/">마을</a><span aria-hidden="true">›</span>
    <a href="${Links.yard(blog.address)}">${escapeHTML(blog.name)}</a><span aria-hidden="true">›</span>
    <span aria-current="page">기록 관리</span>`;
  document.getElementById('tabs').innerHTML = manageTabsHTML('posts');
  if (draftMode) {
    const head = document.querySelector('.manage-row-head');
    head.innerHTML = '<span>임시저장한 기록</span><span>마지막 저장</span><span class="num">관리</span>';
    head.classList.add('draft-row');
  }

  await Promise.all([loadCounts(), draftMode ? loadDrafts() : loadRows()]);
  document.getElementById('gate').hidden = false;
  document.getElementById('house').hidden = false;
}

runPage(main);
