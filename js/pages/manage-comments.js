/**
 * 한채 관리 › 댓글 · 방명록 (CMT-04) /manage-comments
 * manage-comments                  내 기록에 달린 댓글
 * manage-comments?kind=guestbook   받은 방명록
 * 주인은 지우기만 한다 (숨기기는 마을 관리인의 일). 관리인이 숨긴 것은 사유와 함께 보인다.
 */
const params = new URLSearchParams(location.search);
const kind = params.get('kind') === 'guestbook' ? 'guestbook' : 'comments';
const page = Number(params.get('page')) || 1;
const KINDS = [
  { value: 'comments', label: '내 기록에 달린 댓글' },
  { value: 'guestbook', label: '받은 방명록' },
];
let address = '';

async function loadKinds() {
  const [comments, guestbook] = await Promise.all([
    Store.manageComments(address, { size: 1 }),
    Store.manageGuestbook(address, { size: 1 }),
  ]);
  const totals = { comments: comments.total, guestbook: guestbook.total };
  document.getElementById('kinds').innerHTML = KINDS
    .map((k) => `<a href="${Links.manageComments({ kind: k.value })}"${k.value === kind ? ' aria-current="page"' : ''}>${k.label} ${totals[k.value]}</a>`)
    .join('');
}

function rowHTML(item) {
  const gone = item.author.withdrawn;
  const name = gone ? '떠난 사람' : escapeHTML(item.author.nickname);
  const text = item.hidden
    ? `<span>관리인이 숨긴 ${kind === 'comments' ? '댓글' : '방명록'}이에요.</span><span class="talk-hidden">관리인이 숨김 · ${escapeHTML(item.hidden_reason || '')}</span>`
    : `<span title="${escapeHTML(item.content)}">${escapeHTML(item.content)}</span>`;
  const where = kind === 'comments'
    ? `<a class="talk-where text-link" href="${Links.post(address, item.post.no)}">${escapeHTML(item.post.title)}</a>`
    : `<a class="talk-where text-link" href="${Links.guestbook(address)}">방명록</a>`;
  return `
    <div class="talk-row" data-id="${item.id}">
      <span class="talk-who">${avatarHTML(item.author.profile_image_url)}<span class="talk-name${gone ? ' is-gone' : ''}">${name}</span></span>
      <span class="talk-text">${text}</span>
      ${where}
      <span class="talk-date">${formatDate(item.created_at)}</span>
      <button type="button" class="text-link delete" data-delete="${item.id}">삭제</button>
    </div>`;
}

function emptyHTML() {
  return `
    <div class="manage-empty">
      <strong>${kind === 'comments' ? '아직 내 기록에 달린 댓글이 없어요' : '아직 받은 방명록이 없어요'}</strong>
      <span>이웃이 남긴 한마디가 여기에 모여요.</span>
    </div>`;
}

function renderPager(result) {
  const pager = document.getElementById('pager');
  pager.hidden = result.total_pages <= 1;
  if (!pager.hidden) pager.innerHTML = pagerHTML(result, (p) => Links.manageComments({ kind, page: p }));
}

async function loadRows() {
  const load = kind === 'comments' ? Store.manageComments : Store.manageGuestbook;
  let result = await load(address, { page });
  // 지워서 마지막 쪽이 비었으면 앞 쪽을 보인다
  if (!result.items.length && result.page > 1 && result.total_pages) {
    result = await load(address, { page: result.total_pages });
  }
  document.getElementById('rows').innerHTML = result.items.length ? result.items.map(rowHTML).join('') : emptyHTML();
  renderPager(result);
}

document.getElementById('rows').addEventListener('click', async (e) => {
  const button = e.target.closest('[data-delete]');
  if (!button) return;
  const what = kind === 'comments' ? '댓글' : '방명록';
  const ok = await confirmDialog({ title: `이 ${what}을 지울까요?`, text: `지운 ${what}은 되돌릴 수 없어요.`, confirmLabel: '삭제', danger: true });
  if (!ok) return;
  button.disabled = true;
  try {
    if (kind === 'comments') await Store.deleteComment(button.dataset.delete);
    else await Store.deleteGuestbook(button.dataset.delete);
    await Promise.all([loadKinds(), loadRows()]);
  } catch (err) {
    alert(err.firstMessage || err.message);
    button.disabled = false;
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
    <a href="${Links.yard(blog.address)}">${escapeHTML(blog.name)}</a><span aria-hidden="true">›</span>
    <span aria-current="page">댓글 · 방명록</span>`;
  document.getElementById('tabs').innerHTML = manageTabsHTML('comments');
  document.getElementById('where-head').textContent = kind === 'comments' ? '기록' : '어디';

  await Promise.all([loadKinds(), loadRows()]);
  document.getElementById('gate').hidden = false;
  document.getElementById('house').hidden = false;
}

runPage(main);
