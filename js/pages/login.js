/**
 * 로그인 · 가입 (SCR-05)
 * /login?tab=signup 으로 들어오면 가입 탭을, /login?forgot=1 이면 비밀번호 다시 정하기를 연다.
 * /login?next=/주소 로 들어오면 로그인한 뒤 그 주소로 돌아간다.
 * /login?social=... 은 소셜 로그인의 결과다: signup(처음 온 사람의 가입 마무리) · cancelled · error · inactive · suspended
 */
const loginForm = document.getElementById('login-form');
const signupForm = document.getElementById('signup-form');
const forgotForm = document.getElementById('forgot-form');
const socialForm = document.getElementById('social-signup-form');
const tabs = document.querySelectorAll('.login-tabs [role="tab"]');
const params = new URLSearchParams(location.search);

// 다른 사이트로 보내지 않도록 같은 사이트 안의 주소만 받는다 (/\evil.com 같은 것도 브라우저는 다른 사이트로 읽는다)
const next = safeNext(params.get('next'));

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// ----- 탭 -----
// name: login · signup · forgot · social (forgot · social 은 탭이 아니다. 로그인 탭 아래에 연다)
function showTab(name) {
  tabs.forEach((tab) => {
    const selected = tab.dataset.tab === name;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected || (!['login', 'signup'].includes(name) && tab.dataset.tab === 'login') ? 0 : -1;
  });
  loginForm.hidden = name !== 'login';
  signupForm.hidden = name !== 'signup';
  forgotForm.hidden = name !== 'forgot';
  socialForm.hidden = name !== 'social';
  if (name === 'forgot' && !forgotForm.elements.email.value) {
    forgotForm.elements.email.value = loginForm.elements.email.value.trim();
  }
}

document.addEventListener('click', (e) => {
  const button = e.target.closest('[data-tab]');
  if (button) showTab(button.dataset.tab);
});

// 탭끼리 좌우 화살표로 옮겨 다닌다
document.querySelector('.login-tabs').addEventListener('keydown', (e) => {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
  const other = [...tabs].find((tab) => tab.getAttribute('aria-selected') !== 'true');
  showTab(other.dataset.tab);
  other.focus();
});

// ----- 폼 -----
function showError(form, message) {
  form.querySelector('.form-error').textContent = message;
}

// 성공하면 onSuccess(결과), 실패하면 서버가 준 문장을 보여 준다
async function submitWith(form, action, onSuccess) {
  const button = form.querySelector('.form-submit');
  showError(form, '');
  button.disabled = true;
  try {
    const result = await action();
    if (result.ok) {
      onSuccess(result);
    } else {
      showError(form, result.message);
    }
  } catch (err) {
    showError(form, err.message);
  } finally {
    button.disabled = false;
  }
}

// 가입하면 인증 메일이 간다. 인증해야 로그인할 수 있으므로 로그인 탭으로 돌려보낸다
function showVerificationSent(email) {
  showTab('login');
  loginForm.elements.email.value = email;
  const notice = document.getElementById('signup-done');
  notice.querySelector('strong').textContent = email;
  notice.hidden = false;
  showResend();
  loginForm.elements.password.focus();
}

// ----- 인증 메일 다시 보내기 -----
// 로그인 칸에 적힌 이메일로 보낸다. 같은 주소는 1분에 한 번 (서버가 막는다)
const resendBox = document.getElementById('resend');
const resendButton = document.getElementById('resend-button');
const resendStatus = document.getElementById('resend-status');

function showResend() {
  resendBox.hidden = false;
}

resendButton.addEventListener('click', async () => {
  const email = loginForm.elements.email.value.trim();
  if (!EMAIL_PATTERN.test(email)) {
    resendStatus.textContent = '위 로그인 칸에 가입한 이메일을 적어 주세요.';
    loginForm.elements.email.focus();
    return;
  }
  resendButton.disabled = true;
  resendStatus.textContent = '보내는 중이에요…';
  try {
    await Auth.resendVerification(email);
    resendStatus.textContent = `${email} 로 인증 메일을 다시 보냈어요. 스팸함도 확인해 주세요.`;
  } catch (err) {
    resendStatus.textContent = err.firstMessage || err.message;
  } finally {
    // 연달아 누르지 않도록 잠시 뒤에 다시 켠다
    setTimeout(() => { resendButton.disabled = false; }, 3000);
  }
});

loginForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const { email, password } = loginForm.elements;

  if (!EMAIL_PATTERN.test(email.value.trim())) return showError(loginForm, '이메일을 올바르게 입력해 주세요.');
  if (!password.value) return showError(loginForm, '비밀번호를 입력해 주세요.');

  submitWith(loginForm, async () => {
    const result = await Auth.logIn(email.value, password.value);
    // 메일 인증 전이면 다시 보내기를 함께 보여 준다
    if (result.code === 'EMAIL_NOT_VERIFIED') showResend();
    // 이용 제한이면 사유와 기한을 함께 알린다 (ADMIN-02)
    if (result.code === 'SUSPENDED' && result.detail) result.message = suspendedMessage(result.detail);
    return result;
  }, () => { location.href = next; });
});

function agreedToAll(form) {
  const { agreeTerms, agreePrivacy, over14 } = form.elements;
  return agreeTerms.checked && agreePrivacy.checked && over14.checked;
}

signupForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const { nickname, email, password, passwordConfirm, agreeTerms, agreePrivacy, over14 } = signupForm.elements;
  const name = nickname.value.trim();

  if (name.length < 2 || name.length > 20) return showError(signupForm, '닉네임은 2~20자로 입력해 주세요.');
  if (!EMAIL_PATTERN.test(email.value.trim())) return showError(signupForm, '이메일을 올바르게 입력해 주세요.');
  if (password.value.length < 8) return showError(signupForm, '비밀번호는 8자 이상이어야 해요.');
  if (password.value !== passwordConfirm.value) return showError(signupForm, '비밀번호 확인이 맞지 않아요.');
  if (!agreedToAll(signupForm)) return showError(signupForm, '필수 항목에 모두 동의해 주세요.');

  submitWith(signupForm, () => Auth.signUp({
    nickname: name,
    email: email.value,
    password: password.value,
    agreeTerms: agreeTerms.checked,
    agreePrivacy: agreePrivacy.checked,
    over14: over14.checked,
  }), () => showVerificationSent(email.value.trim()));
});

// ----- 비밀번호 다시 정하기 -----
// 가입하지 않은 주소에도 서버는 '보냈어요'로 답한다 (가입 여부를 알려 주지 않는다)
forgotForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const email = forgotForm.elements.email.value.trim();
  const done = document.getElementById('forgot-done');
  done.hidden = true;
  if (!EMAIL_PATTERN.test(email)) return showError(forgotForm, '이메일을 올바르게 입력해 주세요.');

  submitWith(forgotForm, () => Auth.requestPasswordReset(email), () => {
    done.textContent = `${email} 로 가입한 계정이 있으면 비밀번호를 새로 정하는 링크를 보냈어요. 메일이 안 보이면 스팸함도 확인해 주세요.`;
    done.hidden = false;
  });
});

// ----- 소셜 로그인 (AUTH-03) -----
const SOCIAL_MESSAGES = {
  cancelled: '소셜 로그인을 취소했어요.',
  error: '소셜 로그인을 마치지 못했어요. 잠시 뒤 다시 시도해 주세요.',
  inactive: '탈퇴한 계정이에요.',
  suspended: '이용이 제한된 계정이에요.',
};

// 처음 온 사람: 어느 계정으로 왔는지 보이고, 제공사의 이름을 닉네임 칸에 미리 채워 약관 동의를 받는다
const socialNickname = socialForm.elements.nickname;
const socialNicknameStatus = document.getElementById('social-nickname-status');
const NICKNAME_OK_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>';
let socialProviderName = '';
let nicknameCheckTimer = null;

function showNicknameStatus(ok, message) {
  socialNicknameStatus.className = `field-status ${ok ? 'is-ok' : 'is-bad'}`;
  socialNicknameStatus.innerHTML = ok ? `${NICKNAME_OK_ICON}${escapeHTML(message)}` : escapeHTML(message);
  socialNickname.setAttribute('aria-invalid', String(!ok));
}

function clearNicknameStatus() {
  socialNicknameStatus.textContent = '';
  socialNickname.removeAttribute('aria-invalid');
}

// 입력이 멈추면 쓸 수 있는지 본다. 돌려주는 값: 쓸 수 있으면 true (확인하지 못했으면 null, 서버가 가입 때 다시 본다)
async function checkSocialNickname({ prefilled = false } = {}) {
  const nickname = socialNickname.value.trim();
  if (nickname.length < 2 || nickname.length > 20) {
    showNicknameStatus(false, '닉네임은 2~20자로 입력해 주세요.');
    return false;
  }
  let result;
  try {
    result = await Auth.nicknameAvailable(nickname);
  } catch (err) {
    clearNicknameStatus();
    return null;
  }
  if (nickname !== socialNickname.value.trim()) return null; // 그새 바뀌었으면 버린다
  if (!result.available) {
    showNicknameStatus(false, result.reason === 'TAKEN' ? '이미 쓰고 있는 닉네임이에요.' : '쓸 수 없는 닉네임이에요.');
    return false;
  }
  showNicknameStatus(true, prefilled ? `쓸 수 있는 닉네임이에요 · ${socialProviderName}의 이름을 미리 채웠어요` : '쓸 수 있는 닉네임이에요');
  return true;
}

socialNickname.addEventListener('input', () => {
  clearNicknameStatus();
  clearTimeout(nicknameCheckTimer);
  nicknameCheckTimer = setTimeout(checkSocialNickname, 300);
});

function showSocialSignup(signup) {
  socialProviderName = signup.provider_name;
  const mark = document.getElementById('social-account-mark');
  mark.className = `social-account-mark is-${signup.provider}`;
  mark.innerHTML = SOCIAL_PROVIDER_MARKS[signup.provider] || '';
  document.getElementById('social-provider-name').textContent = signup.provider_name;
  document.getElementById('social-account-email').textContent = signup.email || '이메일은 받지 못했어요';
  document.getElementById('social-signup-desc').textContent = signup.email
    ? "닉네임을 정하고 약관에 동의하면 가입이 끝나요. 나중에 '비밀번호를 잊었나요?'에서 비밀번호를 정하면 이메일로도 로그인할 수 있어요."
    : `이메일 없이 가입해요. 비밀번호 재설정 메일은 받을 수 없으니 로그인은 ${signup.provider_name}로 해 주세요.`;
  socialNickname.value = signup.nickname;
  showTab('social');
  socialNickname.focus();
  if (signup.nickname) checkSocialNickname({ prefilled: true });
}

socialForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const { agreeTerms, agreePrivacy, over14 } = socialForm.elements;
  const name = socialNickname.value.trim();
  showError(socialForm, '');

  clearTimeout(nicknameCheckTimer);
  if (await checkSocialNickname() === false) return socialNickname.focus();
  if (!agreedToAll(socialForm)) return showError(socialForm, '필수 항목에 모두 동의해 주세요.');

  submitWith(socialForm, async () => {
    const result = await Auth.finishSocialSignup({
      nickname: name,
      agreeTerms: agreeTerms.checked,
      agreePrivacy: agreePrivacy.checked,
      over14: over14.checked,
    });
    // 가입을 기다리던 정보가 사라졌으면(오래 두었거나 다른 창에서 마쳤으면) 로그인 버튼부터 다시
    if (result.code === 'SOCIAL_SIGNUP_EXPIRED') {
      showTab('login');
      showError(loginForm, result.message);
    }
    // 그새 누가 이 닉네임을 가져갔으면 닉네임 칸 아래에 알린다
    if (result.fields && result.fields.nickname) {
      showNicknameStatus(false, result.fields.nickname);
      socialNickname.focus();
      return { ...result, message: '' };
    }
    return result;
  }, (result) => { location.href = safeNext(result.next); });
});

// 켜진 제공사의 버튼을 그리고, 제공사에서 막 돌아왔으면 결과를 알린다
async function setUpSocialLogin() {
  let status;
  try {
    status = await Auth.socialStatus();
  } catch (err) {
    return; // 소셜 로그인 없이도 이메일 로그인은 된다
  }
  const box = document.getElementById('social-login');
  box.hidden = !renderSocialButtons(document.getElementById('social-buttons'), status.providers, next, { brand: true });

  const result = params.get('social');
  if (result === 'signup') {
    if (status.signup) showSocialSignup(status.signup);
    else showError(loginForm, '소셜 로그인을 처음부터 다시 해 주세요.');
  } else if (result === 'suspended' && status.blocked) {
    showError(loginForm, suspendedMessage(status.blocked));
  } else if (SOCIAL_MESSAGES[result]) {
    showError(loginForm, SOCIAL_MESSAGES[result]);
  }
}
setUpSocialLogin();

// 이미 로그인했으면 돌아갈 곳으로 보낸다. 내 정보를 못 받았으면 로그인 화면에 그대로 둔다
Auth.currentUser().then((user) => {
  if (user) location.replace(next);
}).catch(() => {});
if (params.get('tab') === 'signup') showTab('signup');
if (params.get('forgot') === '1') showTab('forgot');
if (params.get('verified') === '1') document.getElementById('verified-done').hidden = false;
if (params.get('reset') === '1') document.getElementById('reset-done').hidden = false;
// 인증 링크가 만료돼 넘어온 경우 (verify-email 화면)
if (params.get('resend') === '1') showResend();
