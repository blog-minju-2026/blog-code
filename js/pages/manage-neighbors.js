/**
 * 한채 관리 › 이웃 (SUB-04) /manage-neighbors
 * manage-neighbors                내 한채의 이웃 (내보내기)
 * manage-neighbors?kind=blocked   내보낸 이웃 (다시 받아 주기)
 * '이웃 공개' 기록은 이웃과 나만 본다. 누구나 '이웃 맺기'를 누를 수 있으므로, 주인이 여기서 내보내 범위를 정한다.
 * 내보낸 사람은 다시 받아 주기 전까지 이웃을 맺지 못한다.
 */
const params = new URLSearchParams(location.search);
const kind = params.get('kind') === 'blocked' ? 'blocked' : 'neighbors';
const page = Number(params.get('page')) || 1;
const KINDS = [
  { value: 'neighbors', label: '이웃' },
  { value: 'blocked', label: '내보낸 이웃' },
];
const NOTES = {
  neighbors: '내보내면 그 사람은 이웃 공개 기록을 볼 수 없고, 다시 받아 주기 전까지 이웃을 맺지 못해요. 내보냈다는 알림은 가지 않아요.',
  blocked: '다시 받아 주면 그 사람이 다시 이웃을 맺을 수 있어요. 저절로 이웃이 되지는 않아요.',
};
let address = '';

async function loadKinds() {
  const [neighbors, blocked] = await Promise.all([
    Store.manageNeighbors(address, { size: 1 }),
    Store.blockedNeighbors(address, { size: 1 }),
  ]);
  const totals = { neighbors: neighbors.total, blocked: blocked.total };
  document.getElementById('kinds').innerHTML = KINDS
    .map((k) => `<a href="${Links.manageNeighbors({ kind: k.value })}"${k.value === kind ? ' aria-current="page"' : ''}>${k.label} ${totals[k.value]}</a>`)
    .join('');
}

function rowHTML(item) {
  const { user } = item;
  const gone = user.withdrawn;
  const name = gone ? '떠난 사람' : escapeHTML(user.nickname);
  const house = user.blog_address
    ? `<a class="neighbor-house text-link" href="${Links.yard(user.blog_address)}">${escapeHTML(user.blog_address)}</a>`
    : '<span class="neighbor-house is-none">한채 없음</span>';
  const action = kind === 'neighbors'
    ? `<button type="button" class="text-link delete" data-kick="${item.id}" data-name="${name}">내보내기</button>`
    : `<button type="button" class="text-link" data-unblock="${item.id}" data-name="${name}">다시 받아 주기</button>`;
  return `
    <div class="neighbor-row" data-id="${item.id}">
      <span class="talk-who">${avatarHTML(user.profile_image_url)}<span class="talk-name${gone ? ' is-gone' : ''}">${name}</span></span>
      ${house}
      <span class="talk-date">${formatLongDate(kind === 'neighbors' ? item.since : item.blocked_at)}</span>
      ${action}
    </div>`;
}

function emptyHTML() {
  return kind === 'neighbors'
    ? `
    <div class="manage-empty">
      <strong>아직 이웃이 없어요</strong>
      <span>누군가 내 한채에서 '이웃 맺기'를 누르면 여기에 보여요.</span>
    </div>`
    : `
    <div class="manage-empty">
      <strong>내보낸 이웃이 없어요</strong>
      <span>이웃 목록에서 '내보내기'를 누른 사람이 여기에 모여요.</span>
    </div>`;
}

function renderPager(result) {
  const pager = document.getElementById('pager');
  pager.hidden = result.total_pages <= 1;
  if (!pager.hidden) pager.innerHTML = pagerHTML(result, (p) => Links.manageNeighbors({ kind, page: p }));
}

async function loadRows() {
  const load = kind === 'neighbors' ? Store.manageNeighbors : Store.blockedNeighbors;
  let result = await load(address, { page });
  // 내보내서 마지막 쪽이 비었으면 앞 쪽을 보인다
  if (!result.items.length && result.page > 1 && result.total_pages) {
    result = await load(address, { page: result.total_pages });
  }
  document.getElementById('rows').innerHTML = result.items.length ? result.items.map(rowHTML).join('') : emptyHTML();
  renderPager(result);
}

document.getElementById('rows').addEventListener('click', async (e) => {
  const kick = e.target.closest('[data-kick]');
  const unblock = e.target.closest('[data-unblock]');
  const button = kick || unblock;
  if (!button) return;
  // data-name 은 이스케이프해 넣은 값이고, dataset 으로 읽으면 원래 글자로 돌아온다 (확인 창이 다시 이스케이프한다)
  const name = button.dataset.name;
  if (kick) {
    const ok = await confirmDialog({
      title: `${name} 님을 이웃에서 내보낼까요?`,
      text: '내보내면 이웃 공개 기록을 볼 수 없고, 다시 받아 주기 전까지 이웃을 맺지 못해요.',
      confirmLabel: '내보내기',
      danger: true,
    });
    if (!ok) return;
  }
  button.disabled = true;
  try {
    if (kick) await Store.kickNeighbor(address, kick.dataset.kick);
    else await Store.unblockNeighbor(address, unblock.dataset.unblock);
    await Promise.all([loadKinds(), loadRows()]);
  } catch (err) {
    // 그 사이 그 사람이 스스로 이웃을 끊었으면(404) 목록만 다시 그린다
    if (err.status === 404) await Promise.all([loadKinds(), loadRows()]);
    else alert(err.firstMessage || err.message);
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
    <span aria-current="page">이웃</span>`;
  document.getElementById('tabs').innerHTML = manageTabsHTML('neighbors');
  document.getElementById('when-head').textContent = kind === 'neighbors' ? '이웃 맺은 날' : '내보낸 날';
  document.getElementById('kind-note').textContent = NOTES[kind];

  await Promise.all([loadKinds(), loadRows()]);
  document.getElementById('gate').hidden = false;
  document.getElementById('house').hidden = false;
}

runPage(main);
