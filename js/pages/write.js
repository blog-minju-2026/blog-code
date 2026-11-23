/**
 * 글쓰기 (SCR-14)
 * write        새 기록
 * write?no=3   내 한채 3번 기록 수정
 * write?draft=7 임시저장한 기록 이어 쓰기 (임시저장 · 발행)
 * 로그인하지 않았으면 로그인으로, 한채가 없으면 한채 짓기로 보낸다.
 *
 * 쓰던 내용 지키기 (COM-P06)
 * - 브라우저 백업: 입력이 멈추고 2초 뒤 이 브라우저에 적어 둔다. 창이 닫히거나 로그인이 끊겨도 다시 열면 되살릴지 묻는다
 * - 자동 임시저장: 새 기록 · 임시저장 이어 쓰기는 60초마다 서버에 임시저장한다 (다른 기기에서도 이어 쓸 수 있다)
 */
const form = document.getElementById('write-form');
const titleInput = document.getElementById('title');
const roomSelect = document.getElementById('room');
const topicSelect = document.getElementById('topic');
const tagInput = document.getElementById('tag-input');
const thumbPicker = document.getElementById('thumb-picker');
const errorBox = document.getElementById('form-error');
const editNo = Number(new URLSearchParams(location.search).get('no')) || null;
// 임시저장한 기록의 id. 새 기록을 처음 임시저장하면 여기에 들어오고 주소도 ?draft= 로 바뀐다
let draftId = editNo ? null : Number(new URLSearchParams(location.search).get('draft')) || null;
const MAX_TAGS = 10;
// 발행을 연달아 눌러도 한 번만 (API 명세서 2.6)
const clientToken = newClientToken();

let myAddress = '';
let tags = [];
// 올린 사진 주소 → 사진 id. 대표 이미지를 id 로 보내려고 기억해 둔다
const imageIds = new Map();
let coverUrl = '';      // 고른 대표 이미지 주소 ('' 이면 본문 첫 사진)
let uploadedCover = ''; // 본문과 따로 올린 대표 이미지 주소
let isDirty = false;
// 화면을 다 채운 뒤부터 바뀐 것으로 친다 (처음 채우는 동안의 변화는 사람이 쓴 것이 아니다)
let ready = false;

// ----- 쓰던 내용 지키기: 브라우저 백업 -----
const BACKUP_DELAY = 2000;
const AUTOSAVE_EVERY = 60000;
let backupTimer = null;

// 기록마다 따로 둔다: 새 기록 · 임시저장 n번 · 발행한 n번 기록
function backupKey() {
  let which = 'new';
  if (editNo) which = `post-${editNo}`;
  else if (draftId) which = `draft-${draftId}`;
  return `hanchae.write:${myAddress}:${which}`;
}

function readBackup() {
  try {
    const backup = JSON.parse(localStorage.getItem(backupKey()));
    return backup && typeof backup === 'object' ? backup : null;
  } catch (e) {
    return null; // 저장소를 못 쓰거나 값이 깨졌으면 없는 것으로
  }
}

function clearBackup() {
  clearTimeout(backupTimer);
  try {
    localStorage.removeItem(backupKey());
  } catch (e) {
    // 저장소를 못 쓰면 지울 것도 없다
  }
}

function writeBackup() {
  clearTimeout(backupTimer);
  if (!ready || !isDirty) return;
  try {
    localStorage.setItem(backupKey(), JSON.stringify({ ...snapshot(), savedAt: new Date().toISOString() }));
  } catch (e) {
    // 저장소가 꽉 찼거나 막혀 있으면 백업 없이 간다 (나갈 때 경고 · 자동 임시저장은 그대로다)
  }
}

// 바뀌었다고 적고, 입력이 멈추면 백업한다
function markDirty() {
  if (!ready) return;
  isDirty = true;
  clearTimeout(backupTimer);
  backupTimer = setTimeout(writeBackup, BACKUP_DELAY);
}

async function uploadImage(file) {
  const image = await Store.uploadImage(file);
  imageIds.set(image.url, image.id);
  return image.url;
}

const editor = createEditor(document.getElementById('editor'), document.getElementById('toolbar'), { uploadImage });

// ----- 제목 -----
function updateTitleCount() {
  document.getElementById('title-count').textContent = `${titleInput.value.length} / 100`;
}
titleInput.addEventListener('input', updateTitleCount);

// ----- 방 -----
async function renderRooms(selectedId) {
  const { rooms } = await Store.getRooms(myAddress);
  roomSelect.innerHTML = '<option value="">마루 (방 없음)</option>'
    + rooms.map((r) => `<option value="${r.id}">${escapeHTML(r.name)}</option>`).join('');
  roomSelect.value = selectedId ? String(selectedId) : '';
}

document.getElementById('new-room').addEventListener('click', async () => {
  const name = (prompt('새 방 이름을 입력하세요 (1~20자)') || '').trim();
  if (!name) return;
  try {
    const room = await Store.addRoom(myAddress, name);
    await renderRooms(room.id);
    markDirty();
  } catch (err) {
    alert(err.firstMessage || err.message);
  }
});

// ----- 골목 -----
async function renderTopics(selected) {
  try {
    const topics = await Store.getTopics();
    topicSelect.insertAdjacentHTML('beforeend', topics
      .map((t) => `<option value="${escapeHTML(t.slug)}">${escapeHTML(t.name)}</option>`)
      .join(''));
    topicSelect.value = selected || '';
  } catch (e) {
    topicSelect.disabled = true;
  }
}

// ----- 태그 -----
function renderTags() {
  document.getElementById('tag-chips').innerHTML = tags.map((t, i) => `
    <span class="tag">#${escapeHTML(t)}<button type="button" data-remove="${i}" aria-label="${escapeHTML(t)} 태그 빼기">×</button></span>`).join('');
  document.getElementById('tag-count').textContent = `${tags.length} / ${MAX_TAGS}개`;
  tagInput.disabled = tags.length >= MAX_TAGS;
  tagInput.placeholder = tags.length >= MAX_TAGS ? '10개까지 붙일 수 있어요' : '입력 후 Enter';
}

function addTag(raw) {
  const tag = raw.trim().replace(/^#+/, '').replace(/\s+/g, ' ');
  if (!tag || tags.length >= MAX_TAGS) return;
  if (tag.length > 20) {
    alert('태그는 20자까지 쓸 수 있어요.');
    return;
  }
  // 대소문자만 다른 태그는 같은 태그로 본다 (TAG-01)
  if (!tags.some((t) => t.toLowerCase() === tag.toLowerCase())) tags.push(tag);
  renderTags();
  markDirty();
}

tagInput.addEventListener('keydown', (e) => {
  if (e.isComposing) return;
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault();
    addTag(tagInput.value);
    tagInput.value = '';
  } else if (e.key === 'Backspace' && !tagInput.value && tags.length) {
    tags.pop();
    renderTags();
    markDirty();
  }
});

document.getElementById('tag-chips').addEventListener('click', (e) => {
  const button = e.target.closest('[data-remove]');
  if (!button) return;
  tags.splice(Number(button.dataset.remove), 1);
  renderTags();
  markDirty();
  tagInput.focus();
});

// ----- 대표 이미지 -----
function renderThumbPicker() {
  const images = [...new Set([...editor.getImages(), uploadedCover].filter(Boolean))];
  if (coverUrl && !images.includes(coverUrl)) coverUrl = '';
  const current = coverUrl || images[0] || '';
  thumbPicker.innerHTML = images.map((src, i) => `
    <button type="button" role="radio" aria-checked="${src === current}" aria-label="${i + 1}번째 사진을 대표 이미지로">
      <img src="${escapeHTML(src)}" alt="">
    </button>`).join('');
  thumbPicker.querySelectorAll('button').forEach((button, i) => {
    button.addEventListener('click', () => {
      coverUrl = images[i];
      renderThumbPicker();
      markDirty();
    });
  });
}

const coverFile = document.createElement('input');
coverFile.type = 'file';
coverFile.accept = 'image/png, image/jpeg, image/gif, image/webp';
coverFile.addEventListener('change', async () => {
  const file = coverFile.files[0];
  coverFile.value = '';
  if (!file) return;
  try {
    uploadedCover = await uploadImage(file);
    coverUrl = uploadedCover;
    renderThumbPicker();
    markDirty();
  } catch (err) {
    alert(err.message);
  }
});
document.getElementById('thumb-upload').addEventListener('click', () => coverFile.click());

// ----- 사진 놓기 -----
const dropzone = document.getElementById('dropzone');
dropzone.addEventListener('click', () => {
  document.querySelector('[data-action="image"]').click();
});
dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.classList.add('is-over');
});
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('is-over'));
dropzone.addEventListener('drop', async (e) => {
  e.preventDefault();
  dropzone.classList.remove('is-over');
  for (const file of e.dataTransfer.files) {
    await editor.insertImageFile(file);
  }
});

editor.onChange(() => {
  markDirty();
  renderThumbPicker();
});

// 제목 · 방 · 골목 · 공개 범위를 바꿔도 바뀐 것이다 (태그 칸에 치는 중인 글자는 Enter 로 붙일 때 센다)
form.addEventListener('input', (e) => {
  if (e.target !== tagInput) markDirty();
});
form.addEventListener('change', (e) => {
  if (e.target !== tagInput) markDirty();
});

// ----- 발행 -----
function showError(message) {
  errorBox.textContent = message;
}

// 입력칸에서 Enter 를 눌러 실수로 발행되지 않도록 (제목에서는 본문으로)
form.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' || e.target.tagName !== 'INPUT' || e.isComposing) return;
  e.preventDefault();
  if (e.target === titleInput) editor.focus();
});

// 지금 화면에 있는 그대로 (브라우저 백업에 적고, 되살릴 때 그대로 채운다)
function snapshot() {
  return {
    title: titleInput.value,
    content: editor.isEmpty() ? '' : editor.getHTML(),
    category_id: roomSelect.value ? Number(roomSelect.value) : null,
    topic_slug: topicSelect.value || null,
    tags: tags.slice(),
    visibility: form.elements.visibility.value,
    coverUrl,
    uploadedCover,
    images: [...imageIds], // [사진 주소, 사진 id]. 대표 이미지를 id 로 보내는 데 쓴다
  };
}

// 서버에 보낼 내용 (발행 · 임시저장이 같은 칸을 보낸다). 태그 칸에 치다 만 글자도 태그로 붙인다.
// keepTyping: 자동 임시저장은 치는 중인 태그를 건드리지 않는다 (반쯤 친 글자가 태그로 굳지 않게)
function collectData({ keepTyping = false } = {}) {
  if (!keepTyping && tagInput.value.trim()) {
    addTag(tagInput.value);
    tagInput.value = '';
  }
  const now = snapshot();
  return {
    title: now.title.trim(),
    content: now.content,
    category_id: now.category_id,
    topic_slug: now.topic_slug,
    tags: now.tags,
    visibility: now.visibility,
    // 고르지 않았으면 null → 서버가 본문 첫 사진을 쓴다
    cover_image_id: coverUrl ? (imageIds.get(coverUrl) ?? null) : null,
  };
}

// ----- 임시저장 (POST-11): 제목 · 본문이 비어도 저장한다. 발행하기 전까지는 나만 본다 -----
const draftStatus = document.getElementById('draft-status');

function savedTime(iso) {
  return new Date(iso).toLocaleTimeString('ko-KR', { ...KST, hour: 'numeric', minute: '2-digit' });
}

const draftButton = document.getElementById('draft-button');
// 지금 가고 있는 임시저장 요청. 겹쳐 보내지 않고, 발행은 이것이 끝난 뒤에 한다 (새 기록이 두 번 생기지 않게)
let saving = null;
let autosaveOff = false;
let publishing = false;

// auto: 60초마다 저절로 하는 임시저장. 실패해도 쓰는 사람을 붙잡지 않고 상태 줄에만 알린다
async function saveDraftNow({ auto = false } = {}) {
  if (saving) return saving;
  draftButton.disabled = true;
  draftStatus.className = 'draft-status';
  draftStatus.textContent = auto ? '자동으로 임시저장하는 중…' : '임시저장하는 중…';
  saving = (async () => {
    try {
      // 저장하는 사이에 더 쓴 내용은 아직 서버에 없다. 보내기 전에 깃발을 내려 두고, 그 뒤의 변화가 다시 올리게 한다
      const data = collectData({ keepTyping: auto });
      const oldKey = backupKey();
      isDirty = false;
      const saved = await Store.saveDraft(myAddress, data, draftId);
      if (!draftId) {
        draftId = saved.id;
        // 새로고침하거나 나갔다 와도 이 임시저장으로 돌아오게
        history.replaceState(null, '', Links.writeDraft(draftId));
        document.getElementById('write-mode').textContent = '임시저장한 기록 이어 쓰기';
      }
      // 서버에 올라갔으니 브라우저 백업은 필요 없다 (그 사이 더 썼으면 새 열쇠로 다시 적는다)
      try { localStorage.removeItem(oldKey); } catch (e) { /* 저장소를 못 쓰면 지울 것도 없다 */ }
      if (isDirty) writeBackup();
      else clearBackup();
      draftStatus.textContent = `${auto ? '자동으로 ' : ''}임시저장했어요 · ${savedTime(saved.saved_at)}`;
      return true;
    } catch (err) {
      isDirty = true;
      writeBackup(); // 서버에 못 올렸으니 이 브라우저에라도 남긴다
      draftStatus.className = 'draft-status is-bad';
      if (auto) {
        // 로그인이 끊겼거나(401) 임시저장이 꽉 찼으면(400) 60초마다 되풀이하지 않는다. 버튼으로는 다시 해 볼 수 있다
        if (err.status === 401 || err.status === 400) autosaveOff = true;
        const why = err.status === 401 ? '로그인이 끊겼어요' : (err.firstMessage || err.message);
        draftStatus.textContent = `자동 임시저장을 못 했어요 (${why}). 쓰던 내용은 이 브라우저에 남겨 두었어요.`;
      } else {
        draftStatus.textContent = err.firstMessage || err.message;
      }
      return false;
    } finally {
      saving = null;
      draftButton.disabled = false;
    }
  })();
  return saving;
}

draftButton.addEventListener('click', () => {
  showError('');
  autosaveOff = false; // 손으로 다시 해 보면 자동 임시저장도 다시 켠다
  saveDraftNow();
});

// 자동 임시저장: 발행한 기록을 고칠 때는 하지 않는다 (고치는 중인 내용이 임시저장으로 따로 생기면 헷갈린다. 브라우저 백업이 지킨다)
setInterval(() => {
  if (!ready || editNo || autosaveOff || publishing || saving || !isDirty) return;
  // 아무것도 쓰지 않았으면 빈 임시저장을 만들지 않는다
  if (!draftId && !titleInput.value.trim() && editor.isEmpty() && !tags.length) return;
  saveDraftNow({ auto: true });
}, AUTOSAVE_EVERY);

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  showError('');

  const title = titleInput.value.trim();
  if (!title) {
    showError('제목을 입력해 주세요.');
    titleInput.focus();
    return;
  }
  if (editor.isEmpty()) {
    showError('본문을 입력해 주세요.');
    editor.focus();
    return;
  }
  const button = document.getElementById('publish-button');
  button.disabled = true;
  publishing = true; // 발행하는 동안 자동 임시저장이 끼어들지 않게
  try {
    // 가고 있는 임시저장이 있으면 끝나길 기다린다. 그 사이 새 기록이 임시저장(draftId)이 됐을 수 있다
    if (saving) await saving;
    const data = collectData();
    if (!editNo && !draftId) data.client_token = clientToken;
    const saved = draftId
      ? await Store.publishDraft(myAddress, draftId, data)
      : await Store.savePost(myAddress, data, editNo);
    isDirty = false;
    clearBackup();
    location.href = Links.post(myAddress, saved.no);
  } catch (err) {
    showError(err.firstMessage || err.message);
    writeBackup();
    button.disabled = false;
    publishing = false;
  }
});

// 저장하지 않고 나가려 할 때 경고
window.addEventListener('beforeunload', (e) => {
  if (!isDirty) return;
  writeBackup(); // 2초를 기다리던 백업을 바로 적는다
  e.preventDefault();
  e.returnValue = '';
});

// ----- 브라우저 백업 되살리기 -----
// 남겨 둔 내용이 있으면 이어 쓸지 묻는다. 이어 쓰면 { category_id, topic_slug } 를 돌려준다 (방 · 골목 목록을 그릴 때 고른다)
// serverSavedAt: 서버에 임시저장한 시각. 백업이 그보다 오래됐으면 서버의 것이 더 새 내용이다
async function offerBackup(serverSavedAt) {
  const backup = readBackup();
  if (!backup) return null;
  const hasContent = (backup.title || '').trim() || backup.content || (backup.tags || []).length;
  const stale = serverSavedAt && backup.savedAt && new Date(backup.savedAt) <= new Date(serverSavedAt);
  if (!hasContent || stale) {
    clearBackup();
    return null;
  }
  const ok = await confirmDialog({
    title: '쓰던 내용이 남아 있어요',
    text: `${backup.savedAt ? `${formatDateTime(backup.savedAt)}에 ` : ''}이 브라우저에 남겨 둔, 저장하지 않은 내용이에요. 이어서 쓸까요? 취소하면 남겨 둔 내용을 지워요.`,
    confirmLabel: '이어 쓰기',
  });
  if (!ok) {
    clearBackup();
    return null;
  }
  titleInput.value = String(backup.title || '').slice(0, 100);
  editor.setHTML(String(backup.content || '')); // setHTML 이 허용한 태그만 남긴다
  tags = Array.isArray(backup.tags) ? backup.tags.filter((t) => typeof t === 'string').slice(0, MAX_TAGS) : [];
  if (['PUBLIC', 'SUBSCRIBERS', 'PRIVATE'].includes(backup.visibility)) form.elements.visibility.value = backup.visibility;
  (Array.isArray(backup.images) ? backup.images : []).forEach(([url, id]) => imageIds.set(url, id));
  coverUrl = typeof backup.coverUrl === 'string' ? backup.coverUrl : '';
  uploadedCover = typeof backup.uploadedCover === 'string' ? backup.uploadedCover : '';
  return { category_id: backup.category_id || null, topic_slug: backup.topic_slug || null };
}

// ----- 시작 -----
async function main() {
  const user = await Auth.currentUser();
  if (!user) {
    location.replace(Links.login(Links.here()));
    return;
  }
  if (!user.blog_address) {
    location.replace(Links.build());
    return;
  }
  myAddress = user.blog_address;
  const myBlog = await Store.getBlog(myAddress);
  document.getElementById('back-link').href = Links.yard(myAddress);
  document.getElementById('blog-name').textContent = myBlog.name;
  document.getElementById('neighbor-hint').textContent = `내 한채의 이웃 ${myBlog.subscriber_count}명과 나만 볼 수 있어요. 골목 · 새 기록 · 검색에는 나오지 않아요.`;

  let post = null;
  if (editNo) {
    // 발행한 기록을 고칠 때는 임시저장을 쓰지 않는다
    document.getElementById('draft-button').hidden = true;
    draftStatus.hidden = true;
  } else if (draftId) {
    try {
      post = await Store.getDraft(myAddress, draftId);
    } catch (err) {
      if (err.status !== 404) throw err;
      alert('이어 쓸 임시저장 기록을 찾지 못했어요. 이미 발행했거나 지웠을 수 있어요. 새 기록 쓰기로 갈게요.');
      location.replace(Links.write());
      return;
    }
    document.title = '한채 · 임시저장 이어 쓰기';
    document.getElementById('write-mode').textContent = '임시저장한 기록 이어 쓰기';
    const notice = document.getElementById('draft-notice');
    notice.textContent = `${formatDateTime(post.updated_at)}에 임시저장한 기록이에요. 발행하기 전까지는 나만 볼 수 있어요.`;
    notice.hidden = false;
    titleInput.value = post.title;
    editor.setHTML(post.content);
    tags = post.tags.slice();
    form.elements.visibility.value = post.visibility;
    post.images.forEach((img) => imageIds.set(img.url, img.id));
    const cover = post.images.find((img) => img.id === post.cover_image_id);
    if (cover) {
      coverUrl = cover.url;
      if (!editor.getImages().includes(cover.url)) uploadedCover = cover.url;
    }
  }
  if (editNo) {
    post = await Store.getPost(myAddress, editNo);
    if (!post || !post.is_owner) {
      alert('고칠 기록을 찾지 못했어요. 새 기록 쓰기로 갈게요.');
      location.replace(Links.write());
      return;
    }
    document.title = '한채 · 기록 수정';
    document.getElementById('write-mode').textContent = '기록 수정';
    document.getElementById('publish-button').textContent = '고친 내용 발행';
    titleInput.value = post.title;
    editor.setHTML(post.content);
    tags = post.tags.slice();
    form.elements.visibility.value = post.visibility;
    post.images.forEach((img) => imageIds.set(img.url, img.id));
    const cover = post.images.find((img) => img.id === post.cover_image_id);
    if (cover) {
      coverUrl = cover.url;
      if (!editor.getImages().includes(cover.url)) uploadedCover = cover.url;
    }
  }

  // 저장하지 않고 닫았던 내용이 이 브라우저에 남아 있으면 이어 쓸지 묻는다
  const restored = await offerBackup(draftId && post ? post.updated_at : null);
  const chosen = restored || {
    category_id: post && post.category ? post.category.id : null,
    topic_slug: post && post.topic ? post.topic.slug : null,
  };

  await Promise.all([renderRooms(chosen.category_id), renderTopics(chosen.topic_slug)]);
  // 그 사이 없앤 방이면 마루로 (select 에 없는 값을 넣으면 빈 칸이 된다)
  if (roomSelect.selectedIndex < 0) roomSelect.value = '';
  updateTitleCount();
  renderTags();
  renderThumbPicker();
  // 되살린 내용은 아직 서버에 없다. 나갈 때 경고하고 자동 임시저장도 하게 바뀐 것으로 둔다
  isDirty = Boolean(restored);

  form.hidden = false;
  ready = true;
  titleInput.focus();
}

runPage(main);
