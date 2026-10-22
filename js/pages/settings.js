/**
 * 한채 관리 (SCR-18) /settings
 * 한채 이름(현판) · 주인 소개를 바꾼다. 주인 사진은 내 정보의 프로필 사진을 쓴다.
 * 한채 허물기 (BLOG-04): 사라지는 것을 보이고, 한채 주소를 그대로 적어 확인한 뒤 허문다. 계정은 그대로.
 */
const form = document.getElementById('settings-form');
const nameInput = document.getElementById('blog-name-input');
const introInput = document.getElementById('blog-intro-input');
const errorBox = document.getElementById('form-error');
const saved = document.getElementById('saved');
let me = null;
let isDirty = false;

function renderPreview() {
  document.getElementById('preview-name').textContent = nameInput.value.trim() || '한채 이름';
  document.getElementById('preview-intro').textContent = introInput.value.trim() || '주인 소개가 여기에 보여요';
  document.getElementById('name-count').textContent = `${nameInput.value.length} / 40`;
  document.getElementById('intro-count').textContent = `${introInput.value.length} / 200`;
}

[nameInput, introInput].forEach((input) => {
  input.addEventListener('input', () => {
    isDirty = true;
    saved.hidden = true;
    renderPreview();
  });
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errorBox.textContent = '';
  const name = nameInput.value.trim();
  if (!name) {
    errorBox.textContent = '한채 이름을 1~40자로 써 주세요.';
    nameInput.focus();
    return;
  }
  const button = document.getElementById('save-button');
  button.disabled = true;
  try {
    const blog = await Store.updateBlog(me.blog_address, { name, description: introInput.value.trim() });
    // 위의 작은 대문도 새 이름으로
    document.getElementById('gate').innerHTML = ownerGateHTML(blog);
    isDirty = false;
    saved.hidden = false;
  } catch (err) {
    errorBox.textContent = err.firstMessage || err.message;
  } finally {
    button.disabled = false;
  }
});

window.addEventListener('beforeunload', (e) => {
  if (!isDirty) return;
  e.preventDefault();
  e.returnValue = '';
});

// ----- 한채 허물기 -----
const demolishDialog = document.getElementById('demolish-dialog');
const demolishForm = document.getElementById('demolish-form');
let blogAddress = '';

function clearDemolishErrors() {
  document.getElementById('demolish-error').textContent = '';
  document.getElementById('demolish-address-error').textContent = '';
  demolishForm.elements.address.removeAttribute('aria-invalid');
}

document.getElementById('demolish-button').addEventListener('click', async (e) => {
  const button = e.currentTarget;
  button.disabled = true;
  try {
    const s = await Store.demolishSummary(blogAddress);
    document.getElementById('demolish-dialog-title').textContent = `「${s.name}」를 허물까요?`;
    const gone = [`기록 ${s.post_count}개${s.draft_count ? `와 임시저장 ${s.draft_count}개` : ''} · 그 기록의 사진`];
    if (s.room_count) gone.push(`방 ${s.room_count}개`);
    gone.push(`받은 방명록 ${s.guestbook_count}개`, '내 기록에 달린 댓글 · 공감', `이웃 ${s.subscriber_count}명`);
    document.getElementById('demolish-gone').innerHTML = gone.map((item) => `<li>${escapeHTML(item)}</li>`).join('');
    document.getElementById('demolish-address-note').innerHTML = `주소 <strong>${escapeHTML(s.address)}</strong>는 다른 사람이 내 한채인 척하지 못하게 다시 쓸 수 없어요. 새 한채는 다른 주소로 지을 수 있어요.`;
    document.getElementById('demolish-address-label').innerHTML = `확인을 위해 한채 주소 <strong>${escapeHTML(s.address)}</strong>를 그대로 적어 주세요.`;
    demolishForm.reset();
    clearDemolishErrors();
    document.getElementById('demolish-submit').disabled = false;
    demolishDialog.showModal();
    demolishForm.elements.address.focus();
  } catch (err) {
    alert(err.firstMessage || err.message);
  } finally {
    button.disabled = false;
  }
});

document.getElementById('demolish-cancel').addEventListener('click', () => demolishDialog.close());
demolishDialog.addEventListener('click', (e) => {
  if (e.target === demolishDialog) demolishDialog.close(); // 바깥을 누르면 닫는다
});

demolishForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearDemolishErrors();
  const input = demolishForm.elements.address;
  if (input.value.trim() !== blogAddress) {
    document.getElementById('demolish-address-error').textContent = '한채 주소가 맞지 않아요.';
    input.setAttribute('aria-invalid', 'true');
    input.focus();
    return;
  }
  if (!demolishForm.elements.agree.checked) {
    document.getElementById('demolish-error').textContent = '위 내용을 확인했다고 체크해 주세요.';
    return;
  }
  const submit = document.getElementById('demolish-submit');
  submit.disabled = true;
  try {
    await Store.demolishBlog(blogAddress, input.value.trim());
    isDirty = false;
    location.href = '/?demolished=1';
  } catch (err) {
    document.getElementById('demolish-error').textContent = err.firstMessage || err.message;
    submit.disabled = false;
  }
});

async function main() {
  bindVillageSearch(document.getElementById('village-search'));
  const owner = await requireOwner();
  if (!owner) return;
  me = owner.user;
  const { blog } = owner;
  blogAddress = blog.address;
  await renderHeaderNav(document.getElementById('header-nav'));

  document.getElementById('gate').innerHTML = ownerGateHTML(blog);
  document.getElementById('breadcrumb').innerHTML = `
    <a href="/">마을</a><span aria-hidden="true">›</span>
    <a href="${Links.yard(blog.address)}">${escapeHTML(blog.name)}</a><span aria-hidden="true">›</span>
    <span aria-current="page">한채 관리</span>`;
  document.getElementById('tabs').innerHTML = manageTabsHTML('settings');
  document.getElementById('cancel-link').href = Links.yard(blog.address);

  document.getElementById('owner-photo').innerHTML = avatarHTML(me.profile_image_url);
  document.getElementById('preview-photo').innerHTML = avatarHTML(me.profile_image_url);
  document.getElementById('preview-nickname').textContent = me.nickname;
  nameInput.value = blog.name;
  introInput.value = blog.description || '';
  renderPreview();

  document.getElementById('gate').hidden = false;
  document.getElementById('house').hidden = false;
}

runPage(main);
