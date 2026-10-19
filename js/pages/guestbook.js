/**
 * 방명록 (SCR-08) /guestbook?address=minju&page=2
 * 한채에 남기는 한마디. 수정은 쓴 사람만(그 자리에서), 삭제는 쓴 사람과 한채 주인.
 * 헤더 오른쪽에 지금 로그인한 나(사진 · 닉네임)를 보인다 (방명록 시안).
 */
const params = new URLSearchParams(location.search);
const address = params.get('address') || '';
const page = Number(params.get('page')) || 1;
const form = document.getElementById('guest-form');
const textBox = document.getElementById('guest-text');
const listBox = document.getElementById('guest-list');
let entries = [];
let editingId = null;
let clientToken = newClientToken();

function entryHTML(e) {
  const name = e.author.withdrawn ? '떠난 사람' : escapeHTML(e.author.nickname);
  const who = e.author_blog
    ? `<a class="guest-name" href="${Links.yard(e.author_blog.address)}">${name}</a><span class="hyeonpan hyeonpan-sm">${escapeHTML(e.author_blog.name)}</span>`
    : `<span class="guest-name">${name}</span>`;
  const when = `${timeAgo(e.created_at)}${e.edited_at ? ' · 수정됨' : ''}`;
  const tools = `
    ${e.can_edit && e.id !== editingId ? '<button type="button" class="text-link" data-edit>수정</button>' : ''}
    ${e.can_delete ? '<button type="button" class="text-link delete" data-delete>삭제</button>' : ''}`;
  let body;
  if (e.hidden) {
    body = '<p class="guest-text is-hidden">관리자가 숨긴 방명록이에요.</p>';
  } else if (e.id === editingId) {
    body = `
      <form class="guest-edit" data-edit-form novalidate>
        <textarea class="textarea" rows="2" maxlength="1000" aria-label="방명록 수정">${escapeHTML(e.content)}</textarea>
        <p class="form-error-line" role="alert"></p>
        <div class="guest-edit-actions">
          <button type="button" class="btn btn-secondary" data-cancel>취소</button>
          <button type="submit" class="btn btn-primary">저장</button>
        </div>
      </form>`;
  } else {
    body = `<p class="guest-text">${escapeHTML(e.content)}</p>`;
  }
  return `
    <li class="guest-entry" data-id="${e.id}">
      ${avatarHTML(e.author.profile_image_url, 'guest-avatar')}
      <div class="guest-body">
        <div class="guest-meta">${who}<span class="guest-when">${when}</span><span class="guest-tools">${tools}</span></div>
        ${body}
      </div>
    </li>`;
}

function renderList() {
  listBox.innerHTML = entries.length
    ? entries.map(entryHTML).join('')
    : '<li class="guest-empty"><strong>아직 다녀간 흔적이 없어요</strong><span>첫 한마디를 남겨 보세요.</span></li>';
  if (editingId) listBox.querySelector('[data-edit-form] textarea')?.focus();
}

async function loadEntries() {
  const result = await Store.getGuestbook(address, page);
  entries = result.items;
  document.getElementById('guest-count').innerHTML = `다녀간 이웃 <strong>${result.total}</strong>`;
  document.getElementById('pager').innerHTML = pagerHTML(result, (p) => Links.guestbook(address, p));
  renderList();
}

// ----- 남기기 -----
textBox.addEventListener('input', () => {
  document.getElementById('guest-len').textContent = `${textBox.value.length.toLocaleString()} / 1,000`;
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const error = document.getElementById('guest-error');
  error.textContent = '';
  const content = textBox.value.trim();
  if (!content) {
    error.textContent = '한마디를 써 주세요.';
    textBox.focus();
    return;
  }
  const button = document.getElementById('guest-submit');
  button.disabled = true;
  try {
    await Store.addGuestbook(address, content, clientToken);
    clientToken = newClientToken();
    textBox.value = '';
    textBox.dispatchEvent(new Event('input'));
    if (page !== 1) {
      location.href = Links.guestbook(address); // 새 글은 첫 페이지 맨 위에
      return;
    }
    await loadEntries();
  } catch (err) {
    error.textContent = err.firstMessage || err.message;
  } finally {
    button.disabled = false;
  }
});

// ----- 수정 · 삭제 -----
listBox.addEventListener('click', async (e) => {
  const row = e.target.closest('[data-id]');
  if (!row) return;
  const id = Number(row.dataset.id);
  if (e.target.closest('[data-edit]')) {
    editingId = id;
    renderList();
  } else if (e.target.closest('[data-cancel]')) {
    editingId = null;
    renderList();
  } else if (e.target.closest('[data-delete]')) {
    const ok = await confirmDialog({ title: '이 방명록을 지울까요?', text: '지운 방명록은 되돌릴 수 없어요.', confirmLabel: '삭제', danger: true });
    if (!ok) return;
    try {
      await Store.deleteGuestbook(id);
      await loadEntries();
    } catch (err) {
      alert(err.firstMessage || err.message);
    }
  }
});

listBox.addEventListener('submit', async (e) => {
  const editForm = e.target.closest('[data-edit-form]');
  if (!editForm) return;
  e.preventDefault();
  const error = editForm.querySelector('.form-error-line');
  const content = editForm.querySelector('textarea').value.trim();
  if (!content) {
    error.textContent = '한마디를 써 주세요.';
    return;
  }
  try {
    const updated = await Store.editGuestbook(editingId, content);
    entries = entries.map((x) => (x.id === updated.id ? updated : x));
    editingId = null;
    renderList();
  } catch (err) {
    error.textContent = err.firstMessage || err.message;
  }
});

function renderGate(blog, user) {
  document.title = `${blog.name}의 방명록 · 한채`;
  const name = document.getElementById('blog-name');
  name.textContent = blog.name;
  name.href = Links.yard(blog.address);
  const actions = document.getElementById('gate-actions');
  actions.innerHTML = blog.is_owner ? '' : '<button type="button" class="btn" id="neighbor-button"></button>';
  actions.insertAdjacentHTML('beforeend', `<a class="btn btn-secondary" href="${Links.yard(blog.address)}">마당으로</a>`);
  if (!blog.is_owner) bindNeighborButton(document.getElementById('neighbor-button'), blog, () => {});

  document.getElementById('breadcrumb').innerHTML = `
    <a href="/">마을</a><span aria-hidden="true">›</span>
    <a href="${Links.yard(blog.address)}">${escapeHTML(blog.name)}</a><span aria-hidden="true">›</span>
    <span aria-current="page">방명록</span>`;

  if (user) {
    form.hidden = false;
  } else {
    document.getElementById('guest-login').hidden = false;
    document.getElementById('guest-login-link').href = Links.login(Links.here());
  }
}

async function main() {
  bindVillageSearch(document.getElementById('village-search'));
  const [{ user }, blog] = await Promise.all([
    renderHeaderNav(document.getElementById('header-nav')),
    Store.getBlog(address),
  ]);
  if (!blog) {
    showLost('notFound');
    return;
  }
  renderGate(blog, user);
  await loadEntries();
  document.getElementById('gate').hidden = false;
  document.getElementById('house').hidden = false;
}

runPage(main);
