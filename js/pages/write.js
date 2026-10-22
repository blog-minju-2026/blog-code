/**
 * 글쓰기 (SCR-14)
 * write        새 기록
 * write?no=3   내 한채 3번 기록 수정
 * write?draft=7 임시저장한 기록 이어 쓰기 (임시저장 · 발행)
 * 로그인하지 않았으면 로그인으로, 한채가 없으면 한채 짓기로 보낸다.
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
    isDirty = true;
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
  isDirty = true;
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
  }
});

document.getElementById('tag-chips').addEventListener('click', (e) => {
  const button = e.target.closest('[data-remove]');
  if (!button) return;
  tags.splice(Number(button.dataset.remove), 1);
  renderTags();
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
      isDirty = true;
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
    isDirty = true;
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
  isDirty = true;
  renderThumbPicker();
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

// 지금 쓰고 있는 내용 (발행 · 임시저장이 같은 칸을 보낸다)
function collectData() {
  if (tagInput.value.trim()) addTag(tagInput.value);
  return {
    title: titleInput.value.trim(),
    content: editor.isEmpty() ? '' : editor.getHTML(),
    category_id: roomSelect.value ? Number(roomSelect.value) : null,
    topic_slug: topicSelect.value || null,
    tags,
    visibility: form.elements.visibility.value,
    // 고르지 않았으면 null → 서버가 본문 첫 사진을 쓴다
    cover_image_id: coverUrl ? (imageIds.get(coverUrl) ?? null) : null,
  };
}

// ----- 임시저장 (POST-11): 제목 · 본문이 비어도 저장한다. 발행하기 전까지는 나만 본다 -----
const draftStatus = document.getElementById('draft-status');

function savedTime(iso) {
  return new Date(iso).toLocaleTimeString('ko-KR', { ...KST, hour: 'numeric', minute: '2-digit' });
}

document.getElementById('draft-button').addEventListener('click', async (e) => {
  const button = e.currentTarget;
  showError('');
  button.disabled = true;
  draftStatus.className = 'draft-status';
  draftStatus.textContent = '임시저장하는 중…';
  try {
    const saved = await Store.saveDraft(myAddress, collectData(), draftId);
    if (!draftId) {
      draftId = saved.id;
      // 새로고침하거나 나갔다 와도 이 임시저장으로 돌아오게
      history.replaceState(null, '', Links.writeDraft(draftId));
      document.getElementById('write-mode').textContent = '임시저장한 기록 이어 쓰기';
    }
    isDirty = false;
    draftStatus.textContent = `임시저장했어요 · ${savedTime(saved.saved_at)}`;
  } catch (err) {
    draftStatus.className = 'draft-status is-bad';
    draftStatus.textContent = err.firstMessage || err.message;
  } finally {
    button.disabled = false;
  }
});

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
  const data = collectData();
  if (!editNo && !draftId) data.client_token = clientToken;

  const button = document.getElementById('publish-button');
  button.disabled = true;
  try {
    const saved = draftId
      ? await Store.publishDraft(myAddress, draftId, data)
      : await Store.savePost(myAddress, data, editNo);
    isDirty = false;
    location.href = Links.post(myAddress, saved.no);
  } catch (err) {
    showError(err.firstMessage || err.message);
    button.disabled = false;
  }
});

// 저장하지 않고 나가려 할 때 경고
window.addEventListener('beforeunload', (e) => {
  if (!isDirty) return;
  e.preventDefault();
  e.returnValue = '';
});

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

  await Promise.all([
    renderRooms(post && post.category ? post.category.id : null),
    renderTopics(post && post.topic ? post.topic.slug : null),
  ]);
  updateTitleCount();
  renderTags();
  renderThumbPicker();
  isDirty = false;

  form.hidden = false;
  titleInput.focus();
}

runPage(main);
