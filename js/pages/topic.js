/**
 * 골목 (SCR-03) /topic?slug=it
 * 한 골목에 모인 공개 기록을 새 기록부터, '더 불러오기'로 이어서 본다.
 */
const slug = new URLSearchParams(location.search).get('slug') || '';
const STEP = 10;
let cursor = null;
let topic = null;

async function loadMore() {
  const box = document.getElementById('topic-posts');
  const { items, next_cursor: next } = await Store.topicPosts(slug, { cursor, limit: STEP });
  const more = document.getElementById('topic-more');
  if (more) more.remove();
  if (!cursor && !items.length) {
    box.innerHTML = `
      <div class="empty">
        <strong>아직 이 골목에 쌓인 기록이 없어요</strong><br>
        첫 기록을 남기면 이 골목의 첫 집이 돼요.
      </div>`;
    return;
  }
  box.insertAdjacentHTML('beforeend', items.map((p) => villagePostRowHTML(p)).join(''));
  cursor = next;
  if (next) {
    box.insertAdjacentHTML('beforeend', '<button type="button" class="btn btn-secondary list-more" id="topic-more">더 불러오기</button>');
    bindLoadMore(document.getElementById('topic-more'), loadMore);
  }
}

function renderSeat(user) {
  const seat = document.getElementById('seat');
  const pick = `글쓰기에서 골목을 ‘${escapeHTML(topic.name)}’(으)로 고르면 이 골목에도 보여요.`;
  if (!user) {
    seat.innerHTML = `
      <h2 id="seat-title">이 골목에 기록을 남겨 보세요</h2>
      <p>${pick}</p>
      <a class="btn btn-primary btn-block" href="${Links.login(Links.write())}">로그인하고 글쓰기</a>`;
  } else if (!user.blog_address) {
    seat.innerHTML = `
      <h2 id="seat-title">한채를 지으면 기록을 남길 수 있어요</h2>
      <p>${pick}</p>
      <a class="btn btn-primary btn-block" href="${Links.build()}">한채 짓기</a>`;
  } else {
    seat.innerHTML = `
      <h2 id="seat-title">이 골목에 기록을 남겨 보세요</h2>
      <p>${pick}</p>
      <a class="btn btn-primary btn-block" href="${Links.write()}">글쓰기</a>`;
  }
}

async function main() {
  bindVillageSearch(document.getElementById('village-search'));
  const [{ user }, topics] = await Promise.all([
    renderHeaderNav(document.getElementById('header-nav')),
    Store.getTopics(),
  ]);
  topic = topics.find((t) => t.slug === slug);
  if (!topic) {
    showLost('notFound');
    return;
  }

  document.title = `${topic.name} 골목 · 한채`;
  document.getElementById('breadcrumb').innerHTML = `
    <a href="/">마을</a><span aria-hidden="true">›</span><span>골목</span><span aria-hidden="true">›</span>
    <span aria-current="page">${escapeHTML(topic.name)}</span>`;
  document.getElementById('topic-name').textContent = topic.name;
  document.getElementById('topic-desc').textContent = `마을의 한채들이 ${topic.name} 골목에 쌓은 기록이에요. 새 기록부터 보여요.`;
  document.getElementById('topic-chips').innerHTML = topics
    .map((t) => `<a href="${Links.topic(t.slug)}"${t.slug === slug ? ' aria-current="page"' : ''}>${escapeHTML(t.name)}</a>`)
    .join('');
  renderSeat(user);

  await loadMore();
  document.getElementById('house').hidden = false;
}

runPage(main);
