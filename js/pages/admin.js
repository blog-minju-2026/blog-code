/**
 * 마을 관리 (SCR-19) /admin — 서비스 관리자만 (ADMIN-01 · 02 · 03)
 * admin?tab=users&q=      회원 찾기 · 이용 제한 · 해제
 * admin?tab=posts&q=      기록 찾기 · 본문 보기 · 숨기기 · 되돌리기
 * admin?tab=comments&q=   댓글 찾기 · 숨기기 · 되돌리기
 * admin?tab=guestbook&q=  방명록 찾기 · 숨기기 · 되돌리기
 * 모든 처리는 사유를 받아 서버의 관리 기록에 남는다.
 */
const params = new URLSearchParams(location.search);
const TABS = {
  users: { label: '회원', placeholder: '닉네임 · 이메일 · 한채 주소', api: '/api/admin/users' },
  posts: { label: '기록', placeholder: '제목 · 한채 주소나 이름 · 주인 닉네임', api: '/api/admin/posts' },
  comments: { label: '댓글', placeholder: '내용 · 쓴 사람 닉네임 · 한채 주소', api: '/api/admin/comments' },
  guestbook: { label: '방명록', placeholder: '내용 · 쓴 사람 닉네임 · 한채 주소', api: '/api/admin/guestbook' },
};
const tab = TABS[params.get('tab')] ? params.get('tab') : 'users';
const q = (params.get('q') || '').trim();
const page = Number(params.get('page')) || 1;
const VISIBILITY = { PUBLIC: '공개', SUBSCRIBERS: '이웃 공개', PRIVATE: '나만 보기' };
const SANCTION_DAYS = [1, 7, 30];
let items = [];

// ----- 사유를 받는 창 -----
// onSubmit(values) 가 실패하면 창 안에 서버 문장을 보여 주고 그대로 둔다. 성공하면 true, 취소하면 false
function formDialog({ title, text, bodyHTML = '', confirmLabel, danger = false, maxLength = 200, read, onSubmit }) {
  return new Promise((resolve) => {
    const dialog = document.createElement('dialog');
    dialog.className = 'hc-dialog admin-dialog';
    dialog.innerHTML = `
      <form method="dialog" novalidate>
        <h2>${escapeHTML(title)}</h2>
        ${text ? `<p>${escapeHTML(text)}</p>` : ''}
        ${bodyHTML}
        <div class="field-group">
          <label for="admin-reason">사유 <span class="field-hint">(대상자에게 보일 수 있어요)</span></label>
          <textarea class="textarea" id="admin-reason" name="reason" rows="3" maxlength="${maxLength}" required></textarea>
        </div>
        <p class="form-error-line" role="alert"></p>
        <div class="hc-dialog-actions">
          <button type="button" class="btn btn-secondary" value="cancel">취소</button>
          <button type="submit" class="btn ${danger ? 'btn-danger' : 'btn-primary'}">${escapeHTML(confirmLabel)}</button>
        </div>
      </form>`;
    const form = dialog.querySelector('form');
    const error = dialog.querySelector('.form-error-line');
    const close = (ok) => {
      dialog.close();
      dialog.remove();
      resolve(ok);
    };
    dialog.querySelector('[value="cancel"]').addEventListener('click', () => close(false));
    dialog.addEventListener('cancel', (e) => {
      e.preventDefault();
      close(false);
    });
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const reason = form.elements.reason.value.trim();
      if (!reason) {
        error.textContent = '사유를 써 주세요.';
        form.elements.reason.focus();
        return;
      }
      let values = { reason };
      if (read) {
        const extra = read(form);
        if (extra.error) {
          error.textContent = extra.error;
          return;
        }
        values = { ...values, ...extra };
      }
      const submit = form.querySelector('[type="submit"]');
      submit.disabled = true;
      error.textContent = '';
      try {
        await onSubmit(values);
        close(true);
      } catch (err) {
        error.textContent = err.firstMessage || err.message;
        submit.disabled = false;
      }
    });
    document.body.appendChild(dialog);
    dialog.showModal();
    form.elements.reason.focus();
  });
}

// 기간: 1일 · 7일 · 30일 · 영구 · 날짜 고르기
function sanctionPeriodHTML() {
  const today = new Date().toLocaleDateString('sv-SE', KST); // YYYY-MM-DD
  const option = (value, label, checked = false) => `
    <label class="period-option"><input type="radio" name="period" value="${value}"${checked ? ' checked' : ''}><span>${label}</span></label>`;
  return `
    <fieldset class="field-group period">
      <legend class="field-label">기간</legend>
      <div class="period-options">
        ${SANCTION_DAYS.map((d, i) => option(d, `${d}일`, i === 1)).join('')}
        ${option('forever', '영구')}
        ${option('date', '날짜 고르기')}
      </div>
      <input class="input" type="date" name="until" min="${today}" aria-label="제한이 끝나는 날" hidden>
      <span class="field-hint">고른 날 밤 12시(한국 시간)에 저절로 풀려요.</span>
    </fieldset>`;
}

function readSanctionPeriod(form) {
  const period = form.elements.period.value;
  if (period === 'forever') return { ends_at: null };
  if (period === 'date') {
    const until = form.elements.until.value;
    if (!until) return { error: '끝나는 날을 골라 주세요.' };
    // 고른 날이 끝날 때까지 (한국 시간)
    const end = new Date(`${until}T00:00:00+09:00`);
    end.setDate(end.getDate() + 1);
    return { ends_at: end.toISOString() };
  }
  return { ends_at: new Date(Date.now() + Number(period) * 24 * 60 * 60 * 1000).toISOString() };
}

// ----- 행 -----
function hiddenMarkHTML(hidden) {
  if (!hidden) return '';
  return `<span class="private-mark">숨김 · ${escapeHTML(hidden.reason)} <span class="admin-sub">(${escapeHTML(hidden.by || '관리자')}, ${formatDateTime(hidden.at)})</span></span>`;
}

function hideButtonHTML(item, index) {
  return item.hidden
    ? `<button type="button" class="btn btn-secondary" data-action="unhide" data-index="${index}">되돌리기</button>`
    : `<button type="button" class="btn btn-danger-outline" data-action="hide" data-index="${index}">숨기기</button>`;
}

function userRowHTML(u, index) {
  const blog = u.blog ? `<a class="text-link" href="${Links.yard(u.blog.address)}">${escapeHTML(u.blog.name)}</a>` : '한채 없음';
  let status = '';
  let tools = `<button type="button" class="btn btn-danger-outline" data-action="sanction" data-index="${index}">이용 제한</button>`;
  if (u.role === 'ADMIN') {
    status = '<span class="room-label">관리자</span>';
    tools = '';
  } else if (u.sanction) {
    const until = u.sanction.ends_at ? `${formatDateTime(u.sanction.ends_at)}까지` : '영구';
    status = `<span class="private-mark">이용 제한 중 · ${until} · ${escapeHTML(u.sanction.reason)}</span>`;
    tools = `<button type="button" class="btn btn-secondary" data-action="release" data-index="${index}">제한 풀기</button>`;
  }
  return `
    <div class="admin-row">
      <div class="admin-main">
        <strong>${escapeHTML(u.nickname || '(닉네임 없음)')}</strong>
        <span class="admin-sub">${escapeHTML(u.email || '')} · ${formatLongDate(u.created_at)} 가입 · ${blog}</span>
        ${status}
      </div>
      <div class="admin-tools">${tools}</div>
    </div>`;
}

function postRowHTML(p, index) {
  return `
    <div class="admin-row">
      <div class="admin-main">
        <strong>${escapeHTML(p.title || '(제목 없음)')}</strong>
        <span class="admin-sub">${escapeHTML(p.blog.name)} (${escapeHTML(p.blog.address)}) · ${escapeHTML(p.author.nickname || '')} · ${VISIBILITY[p.visibility] || p.visibility} · ${formatLongDate(p.published_at)}</span>
        ${hiddenMarkHTML(p.hidden)}
      </div>
      <div class="admin-tools">
        <button type="button" class="btn btn-secondary" data-action="read" data-index="${index}">본문 보기</button>
        ${hideButtonHTML(p, index)}
      </div>
    </div>`;
}

function commentRowHTML(c, index) {
  const where = tab === 'comments'
    ? `<a class="text-link" href="${Links.post(c.post.blog_address, c.post.no)}">${escapeHTML(c.post.title)}</a>`
    : `<a class="text-link" href="${Links.guestbook(c.blog.address)}">${escapeHTML(c.blog.name)} 방명록</a>`;
  return `
    <div class="admin-row">
      <div class="admin-main">
        <p class="admin-text">${escapeHTML(c.content)}</p>
        <span class="admin-sub">${escapeHTML(c.author.nickname || '떠난 사람')} · ${formatDateTime(c.created_at)} · ${where}</span>
        ${hiddenMarkHTML(c.hidden)}
      </div>
      <div class="admin-tools">${hideButtonHTML(c, index)}</div>
    </div>`;
}

const ROW = { users: userRowHTML, posts: postRowHTML, comments: commentRowHTML, guestbook: commentRowHTML };

async function loadRows() {
  const query = new URLSearchParams();
  if (q) query.set('q', q);
  if (page > 1) query.set('page', page);
  const result = await Api.get(`${TABS[tab].api}?${query}`);
  items = result.items;
  document.getElementById('rows').innerHTML = items.length
    ? items.map((item, i) => ROW[tab](item, i)).join('')
    : `<p class="empty">${q ? `‘${escapeHTML(q)}’에 맞는 ${TABS[tab].label}이(가) 없어요.` : `아직 ${TABS[tab].label}이(가) 없어요.`}</p>`;
  const pager = document.getElementById('pager');
  pager.innerHTML = pagerHTML(result, (p) => Links.admin(tab, { q, page: p }));
  pager.hidden = result.total_pages <= 1;
}

// ----- 처리 -----
const HIDE_PATH = { posts: 'posts', comments: 'comments', guestbook: 'guestbook' };
const TARGET_NAME = { posts: '기록', comments: '댓글', guestbook: '방명록' };

async function readPost(post) {
  const detail = await Api.get(`/api/admin/posts/${post.id}`);
  const dialog = document.createElement('dialog');
  dialog.className = 'hc-dialog admin-dialog admin-dialog-wide';
  const comments = detail.comments.length
    ? detail.comments.map((c) => `
        <li>
          <span class="admin-sub">${escapeHTML(c.author.nickname || '떠난 사람')} · ${formatDateTime(c.created_at)}</span>
          <p class="admin-text">${escapeHTML(c.content)}</p>
          ${hiddenMarkHTML(c.hidden)}
        </li>`).join('')
    : '<li class="admin-sub">댓글이 없어요.</li>';
  dialog.innerHTML = `
    <h2>${escapeHTML(detail.title)}</h2>
    <p>${escapeHTML(detail.blog.name)} · ${escapeHTML(detail.author.nickname || '')} · ${VISIBILITY[detail.visibility] || ''} · ${formatLongDate(detail.published_at)}</p>
    ${hiddenMarkHTML(detail.hidden)}
    <div class="post-content admin-body">${sanitizeHTML(detail.content)}</div>
    <h3 class="field-label">댓글 ${detail.comments.length}</h3>
    <ul class="admin-comments">${comments}</ul>
    <div class="hc-dialog-actions"><button type="button" class="btn btn-secondary" value="close">닫기</button></div>`;
  const close = () => {
    dialog.close();
    dialog.remove();
  };
  dialog.querySelector('[value="close"]').addEventListener('click', close);
  dialog.addEventListener('close', () => dialog.remove());
  document.body.appendChild(dialog);
  dialog.showModal();
}

async function act(action, item) {
  if (action === 'read') return readPost(item);
  if (action === 'sanction') {
    return formDialog({
      title: `${item.nickname} 님의 이용을 제한할까요?`,
      text: '제한하는 동안 로그인할 수 없고, 이 회원의 한채와 기록은 다른 사람에게 보이지 않아요.',
      bodyHTML: sanctionPeriodHTML(),
      confirmLabel: '이용 제한',
      danger: true,
      maxLength: 500,
      read: readSanctionPeriod,
      onSubmit: (values) => Api.post(`/api/admin/users/${item.id}/sanctions`, values),
    });
  }
  if (action === 'release') {
    return formDialog({
      title: `${item.nickname} 님의 이용 제한을 풀까요?`,
      text: '풀면 바로 로그인할 수 있고, 한채와 기록이 다시 보여요.',
      confirmLabel: '제한 풀기',
      maxLength: 500,
      onSubmit: (values) => Api.post(`/api/admin/users/${item.id}/release`, values),
    });
  }
  const name = TARGET_NAME[tab];
  const hide = action === 'hide';
  return formDialog({
    title: hide ? `이 ${name}을(를) 숨길까요?` : `이 ${name}을(를) 다시 보이게 할까요?`,
    text: hide
      ? (tab === 'posts'
        ? '다른 사람에게는 없는 기록이 되고, 주인에게는 숨김 사실과 사유가 보여요.'
        : `다른 사람에게는 ‘관리자가 숨긴 ${name}’로 보여요.`)
      : '숨김을 되돌리면 원래대로 보여요. 사유는 관리 기록에만 남아요.',
    confirmLabel: hide ? '숨기기' : '되돌리기',
    danger: hide,
    onSubmit: (values) => Api.post(`/api/admin/${HIDE_PATH[tab]}/${item.id}/${action}`, values),
  });
}

document.getElementById('rows').addEventListener('click', async (e) => {
  const button = e.target.closest('[data-action]');
  if (!button) return;
  button.disabled = true;
  try {
    const done = await act(button.dataset.action, items[Number(button.dataset.index)]);
    if (done) await loadRows();
  } catch (err) {
    alert(err.firstMessage || err.message);
  } finally {
    button.disabled = false;
  }
});

// '날짜 고르기'를 고를 때만 날짜 칸을 보인다
document.addEventListener('change', (e) => {
  if (e.target.name !== 'period') return;
  const until = e.target.form.elements.until;
  until.hidden = e.target.value !== 'date';
  if (!until.hidden) until.focus();
});

async function main() {
  bindVillageSearch(document.getElementById('village-search'));
  const user = await Auth.currentUser();
  if (!user) {
    location.replace(Links.login(Links.here()));
    return;
  }
  await renderHeaderNav(document.getElementById('header-nav'));
  if (user.role !== 'ADMIN') {
    showLost('forbidden', { text: '마을 관리인만 들어갈 수 있는 곳이에요.' });
    return;
  }

  document.getElementById('tabs').innerHTML = Object.entries(TABS)
    .map(([key, t]) => `<a href="${Links.admin(key)}"${key === tab ? ' aria-current="page"' : ''}>${t.label}</a>`)
    .join('');
  const search = document.getElementById('admin-search');
  search.elements.q.value = q;
  search.elements.q.placeholder = TABS[tab].placeholder;
  search.addEventListener('submit', (e) => {
    e.preventDefault();
    location.href = Links.admin(tab, { q: search.elements.q.value.trim() });
  });

  await loadRows();
  document.getElementById('house').hidden = false;
}

runPage(main);
