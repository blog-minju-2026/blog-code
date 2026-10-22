/**
 * 이웃 (SCR-12) /neighbors
 * 왼쪽: 이웃 소식(이웃 한채의 새 기록, 더 불러오기). 오른쪽: 내 이웃 목록과 이웃 끊기.
 */
const FEED_STEP = 10;
const NEIGHBOR_STEP = 10;
let feedCursor = null;
let neighborTotal = 0;
const shownNeighbors = new Set();

async function loadFeed() {
  const box = document.getElementById('feed');
  const { items, next_cursor: next } = await Store.neighborFeed({ cursor: feedCursor, limit: FEED_STEP });
  document.getElementById('feed-more')?.remove();
  if (!feedCursor && !items.length) {
    box.innerHTML = `
      <div class="empty">
        <strong>아직 이웃 소식이 없어요</strong><br>
        이웃을 맺으면 이웃 한채의 새 기록이 여기 모여요.
      </div>`;
    return;
  }
  box.insertAdjacentHTML('beforeend', items.map((p) => villagePostRowHTML(p)).join(''));
  feedCursor = next;
  if (next) {
    box.insertAdjacentHTML('beforeend', '<button type="button" class="btn btn-secondary list-more" id="feed-more">더 불러오기</button>');
    bindLoadMore(document.getElementById('feed-more'), loadFeed);
  }
}

function neighborHTML(b) {
  return `
    <div class="neighbor-row" data-address="${escapeHTML(b.address)}">
      ${avatarHTML(b.profile_image_url)}
      <a class="neighbor-row-text" href="${Links.yard(b.address)}">
        <span class="neighbor-row-name">${escapeHTML(b.name)}</span>
        <span class="neighbor-row-meta">${escapeHTML(b.owner.nickname || '떠난 사람')} · 기록 ${b.post_count}</span>
      </a>
      <button type="button" class="btn btn-secondary neighbor-cut" data-cut>이웃 끊기</button>
    </div>`;
}

function paintTotal() {
  document.getElementById('neighbor-total').textContent = neighborTotal;
  const list = document.getElementById('neighbor-list');
  if (!neighborTotal) {
    list.innerHTML = `
      <div class="neighbor-empty">
        <strong>아직 맺은 이웃이 없어요</strong>
        <span>마음에 드는 한채의 대문에서 ‘이웃 맺기’를 누르면 새 기록이 여기 모여요.</span>
        <a class="text-link" href="/">마을 둘러보기</a>
      </div>`;
  }
}

// 끊은 이웃은 서버 목록에서 빠져 페이지가 당겨진다. 그래서 아직 이웃인 줄 수로 다음 페이지를 정하고, 겹치는 줄은 거른다
async function loadNeighbors() {
  const list = document.getElementById('neighbor-list');
  const active = list.querySelectorAll('.neighbor-row:not(.is-cut)').length;
  const result = await Store.myNeighbors({ page: Math.floor(active / NEIGHBOR_STEP) + 1, size: NEIGHBOR_STEP });
  neighborTotal = result.total;
  document.getElementById('neighbor-more')?.remove();
  const fresh = result.items.filter((b) => !shownNeighbors.has(b.address));
  fresh.forEach((b) => shownNeighbors.add(b.address));
  list.insertAdjacentHTML('beforeend', fresh.map(neighborHTML).join(''));
  if (active + fresh.length < result.total) {
    list.insertAdjacentHTML('beforeend', '<button type="button" class="text-link neighbor-more" id="neighbor-more">더 보기</button>');
    bindLoadMore(document.getElementById('neighbor-more'), loadNeighbors);
  }
  paintTotal();
}

// 이웃 끊기: 한 번 더 누르면 다시 맺을 수 있게 그 자리에 둔다
document.getElementById('neighbor-list').addEventListener('click', async (e) => {
  const button = e.target.closest('[data-cut]');
  if (!button) return;
  const row = button.closest('[data-address]');
  const cut = !row.classList.contains('is-cut');
  button.disabled = true;
  try {
    await Store.setNeighbor(row.dataset.address, !cut);
    row.classList.toggle('is-cut', cut);
    button.textContent = cut ? '다시 맺기' : '이웃 끊기';
    neighborTotal += cut ? -1 : 1;
    document.getElementById('neighbor-total').textContent = neighborTotal;
  } catch (err) {
    alert(err.firstMessage || err.message);
  } finally {
    button.disabled = false;
  }
});

async function main() {
  bindVillageSearch(document.getElementById('village-search'));
  const user = await Auth.currentUser();
  if (!user) {
    location.replace(Links.login(Links.here()));
    return;
  }
  await renderHeaderNav(document.getElementById('header-nav'));
  await Promise.all([loadFeed(), loadNeighbors()]);
  document.getElementById('house').hidden = false;
}

runPage(main);
