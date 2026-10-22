/**
 * 내 정보 (SCR-11) /me
 * 닉네임 · 프로필 사진(대문의 주인 사진도 이 사진) · 로그아웃 · 탈퇴.
 * 사진은 올리거나 지우는 즉시 저장하고, 닉네임은 '저장'을 눌러 저장한다.
 */
const form = document.getElementById('me-form');
const nicknameInput = document.getElementById('nickname');
const nicknameStatus = document.getElementById('nickname-status');
const photoStatus = document.getElementById('photo-status');
const errorBox = document.getElementById('form-error');
const saved = document.getElementById('saved');
const CHECK_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>';
let me = null;
let nicknameOk = true;

function setStatus(box, ok, html) {
  box.className = `field-status ${ok ? 'is-ok' : 'is-bad'}`;
  box.innerHTML = html;
}

// ----- 사진 -----
function renderPhoto() {
  document.getElementById('photo').innerHTML = avatarHTML(me.profile_image_url);
  document.getElementById('photo-remove').hidden = !me.profile_image_url;
}

async function savePhoto(imageId, message) {
  photoStatus.textContent = '저장하는 중이에요…';
  photoStatus.className = 'field-status';
  try {
    me = await Store.updateMe({ profile_image_id: imageId });
    renderPhoto();
    setStatus(photoStatus, true, `${CHECK_ICON}${message}`);
  } catch (err) {
    setStatus(photoStatus, false, escapeHTML(err.firstMessage || err.message));
  }
}

const photoFile = document.createElement('input');
photoFile.type = 'file';
photoFile.accept = 'image/png, image/jpeg, image/gif, image/webp';
photoFile.addEventListener('change', async () => {
  const file = photoFile.files[0];
  photoFile.value = '';
  if (!file) return;
  try {
    const image = await Store.uploadImage(file);
    await savePhoto(image.id, '사진을 바꿨어요');
  } catch (err) {
    setStatus(photoStatus, false, escapeHTML(err.firstMessage || err.message));
  }
});
document.getElementById('photo-change').addEventListener('click', () => photoFile.click());
document.getElementById('photo-remove').addEventListener('click', () => savePhoto(null, '사진을 지웠어요'));

// ----- 닉네임: 입력이 멈추면 쓸 수 있는지 본다 -----
let checkTimer = null;
async function checkNickname() {
  const nickname = nicknameInput.value.trim();
  if (nickname === me.nickname) {
    nicknameOk = true;
    nicknameStatus.textContent = '';
    return;
  }
  if (nickname.length < 2 || nickname.length > 20) {
    nicknameOk = false;
    setStatus(nicknameStatus, false, '닉네임은 2~20자로 써 주세요.');
    return;
  }
  const result = await Store.nicknameAvailable(nickname);
  if (nickname !== nicknameInput.value.trim()) return; // 그새 바뀌었으면 버린다
  nicknameOk = result.available;
  setStatus(nicknameStatus, result.available, result.available
    ? `${CHECK_ICON}쓸 수 있는 닉네임이에요`
    : '이미 쓰고 있는 닉네임이에요.');
}

nicknameInput.addEventListener('input', () => {
  saved.hidden = true;
  nicknameOk = false;
  clearTimeout(checkTimer);
  checkTimer = setTimeout(checkNickname, 300);
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errorBox.textContent = '';
  clearTimeout(checkTimer);
  await checkNickname();
  if (!nicknameOk) {
    nicknameInput.focus();
    return;
  }
  const nickname = nicknameInput.value.trim();
  if (nickname === me.nickname) {
    saved.hidden = false;
    return;
  }
  const button = document.getElementById('save-button');
  button.disabled = true;
  try {
    me = await Store.updateMe({ nickname });
    nicknameStatus.textContent = '';
    saved.hidden = false;
    await renderHeaderNav(document.getElementById('header-nav'));
  } catch (err) {
    errorBox.textContent = err.firstMessage || err.message;
  } finally {
    button.disabled = false;
  }
});

document.getElementById('logout-button').addEventListener('click', async () => {
  try {
    await Auth.logOut();
    location.href = '/';
  } catch (err) {
    alert(err.message);
  }
});

// ----- 탈퇴 (AUTH-06): 사라지는 것 · 남는 것을 보여 주고 비밀번호(없으면 닉네임)로 확인한다 -----
const leaveDialog = document.getElementById('leave-dialog');
const leaveForm = document.getElementById('leave-form');
const leaveError = document.getElementById('leave-error');
let leaveConfirmWith = 'password';

function leaveField(name) {
  return { input: leaveForm.elements[name], error: document.getElementById(`leave-${name}-error`) };
}

function showLeaveFieldError(name, message) {
  const { input, error } = leaveField(name);
  error.textContent = message;
  input.setAttribute('aria-invalid', 'true');
  input.focus();
}

function clearLeaveErrors() {
  leaveError.textContent = '';
  ['password', 'nickname'].forEach((name) => {
    const { input, error } = leaveField(name);
    error.textContent = '';
    input.removeAttribute('aria-invalid');
  });
}

// '민주를' · '서현을'처럼 끝 글자의 받침에 맞는 조사 (한글이 아니면 '를')
function objectParticle(word) {
  const code = word.charCodeAt(word.length - 1) - 0xac00;
  return code >= 0 && code <= 11171 && code % 28 ? '을' : '를';
}

function fillLeaveDialog(summary) {
  const provider = summary.social_provider;
  const gone = [];
  if (summary.blog) {
    gone.push(`내 한채 「${escapeHTML(summary.blog.name)}」`);
    gone.push(`기록 ${summary.post_count}개와 올린 사진`);
    gone.push(`방 · 받은 방명록 · 이웃 ${summary.subscriber_count}명`);
  } else {
    gone.push('올린 사진');
  }
  gone.push('내가 맺은 이웃 · 누른 공감');
  gone.push(provider ? `내 정보와 ${escapeHTML(provider)} 계정 연결` : '내 정보 (이메일 · 닉네임 · 사진)');
  document.getElementById('leave-gone').innerHTML = gone.map((item) => `<li>${item}</li>`).join('');

  const stay = [];
  if (summary.comment_count) stay.push(`다른 한채에 남긴 댓글 ${summary.comment_count}개`);
  if (summary.guestbook_count) stay.push(`다른 한채에 남긴 방명록 ${summary.guestbook_count}개`);
  document.getElementById('leave-stay').innerHTML = stay.length
    ? stay.map((item) => `<li>${item}</li>`).join('')
    : '<li>남는 것이 없어요</li>';
  document.getElementById('leave-stay-hint').hidden = !stay.length;

  document.getElementById('leave-again').textContent = provider
    ? `같은 ${provider} 계정으로 다시 가입할 수는 있지만, 지금의 한채와 기록은 돌아오지 않아요.`
    : '같은 이메일로 다시 가입할 수는 있지만, 지금의 한채와 기록은 돌아오지 않아요.';

  // 비밀번호가 있으면 비밀번호, 없으면(소셜로만 가입) 닉네임을 그대로 적어 확인한다
  leaveConfirmWith = summary.confirm_with;
  document.getElementById('leave-password-group').hidden = leaveConfirmWith !== 'password';
  document.getElementById('leave-nickname-group').hidden = leaveConfirmWith !== 'nickname';
  document.getElementById('leave-nickname-label').innerHTML = `${escapeHTML(provider || '소셜 계정')}로 가입해 비밀번호가 없어요. `
    + `확인을 위해 닉네임 <strong>${escapeHTML(summary.nickname)}</strong>${objectParticle(summary.nickname)} 그대로 적어 주세요.`;
}

document.getElementById('leave-button').addEventListener('click', async (e) => {
  const button = e.currentTarget;
  button.disabled = true;
  try {
    const summary = await Store.leaveSummary();
    // 마을 관리인은 탈퇴할 수 없다. 비밀번호까지 넣게 하지 않고 바로 알린다
    if (!summary.can_leave) {
      alert('마을 관리인은 탈퇴할 수 없어요. 다른 관리인에게 역할을 넘긴 뒤 탈퇴해 주세요.');
      return;
    }
    fillLeaveDialog(summary);
    leaveForm.reset();
    clearLeaveErrors();
    leaveDialog.showModal();
    leaveField(leaveConfirmWith).input.focus();
  } catch (err) {
    alert(err.firstMessage || err.message);
  } finally {
    button.disabled = false;
  }
});

document.getElementById('leave-cancel').addEventListener('click', () => leaveDialog.close());
leaveDialog.addEventListener('click', (e) => {
  if (e.target === leaveDialog) leaveDialog.close(); // 바깥을 누르면 닫는다
});

leaveForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearLeaveErrors();
  const value = leaveField(leaveConfirmWith).input.value;
  if (!value.trim()) {
    return showLeaveFieldError(leaveConfirmWith, leaveConfirmWith === 'password' ? '비밀번호를 입력해 주세요.' : '닉네임을 적어 주세요.');
  }
  if (!leaveForm.elements.agree.checked) {
    leaveError.textContent = '위 내용을 확인했다고 체크해 주세요.';
    return;
  }

  const submit = document.getElementById('leave-submit');
  submit.disabled = true;
  try {
    await Store.leave(leaveConfirmWith === 'password' ? { password: value } : { nickname: value.trim() });
    location.href = '/?left=1';
  } catch (err) {
    const field = ['password', 'nickname'].find((name) => err.fields && err.fields[name]);
    if (field) showLeaveFieldError(field, err.fields[field]);
    else leaveError.textContent = err.firstMessage || err.message;
    submit.disabled = false;
  }
});

// ----- 오른쪽: 내 한채 -----
async function renderMyHouse() {
  const box = document.getElementById('my-house');
  const blog = me.blog_address ? await Store.getBlog(me.blog_address) : null;
  box.innerHTML = blog
    ? `
      <section class="card my-house" aria-labelledby="my-house-title">
        <div class="giwa giwa-thin" aria-hidden="true"></div>
        <div class="dancheong-band" aria-hidden="true"></div>
        <div class="my-house-body">
          <h2 id="my-house-title">내 한채</h2>
          <span class="hyeonpan">${escapeHTML(blog.name)}</span>
          <span class="meta">이웃 ${blog.subscriber_count} · 기록 ${blog.post_count}</span>
          <div class="my-house-actions">
            <a class="btn btn-secondary" href="${Links.yard(blog.address)}">내 마당</a>
            <a class="btn btn-primary" href="${Links.settings()}">한채 관리</a>
          </div>
        </div>
      </section>`
    : `
      <section class="card my-house" aria-labelledby="my-house-title">
        <div class="giwa giwa-thin" aria-hidden="true"></div>
        <div class="dancheong-band" aria-hidden="true"></div>
        <div class="my-house-body">
          <h2 id="my-house-title">아직 지은 한채가 없어요</h2>
          <span class="meta">한채를 지으면 기록을 쌓고 이웃을 맺을 수 있어요.</span>
          <div class="my-house-actions"><a class="btn btn-primary" href="${Links.build()}">한채 짓기</a></div>
        </div>
      </section>`;
}

async function main() {
  bindVillageSearch(document.getElementById('village-search'));
  me = await Auth.currentUser();
  if (!me) {
    location.replace(Links.login(Links.here()));
    return;
  }
  await renderHeaderNav(document.getElementById('header-nav'));
  nicknameInput.value = me.nickname;
  // 소셜 계정으로 가입하며 이메일을 받지 못한 회원은 이메일이 없다
  document.getElementById('email').textContent = me.email || '없음';
  document.getElementById('email-verified').hidden = !me.email;
  if (!me.email) document.getElementById('email-hint').textContent = '소셜 계정으로 가입해 이메일 없이 로그인해요.';
  renderPhoto();
  await renderMyHouse();
  document.getElementById('house').hidden = false;
}

runPage(main);
