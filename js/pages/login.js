/**
 * 로그인 · 가입 (SCR-05)
 * /login?tab=signup 으로 들어오면 가입 탭을 연다.
 * /login?next=/주소 로 들어오면 로그인한 뒤 그 주소로 돌아간다.
 */
const loginForm = document.getElementById('login-form');
const signupForm = document.getElementById('signup-form');
const tabs = document.querySelectorAll('.login-tabs [role="tab"]');
const params = new URLSearchParams(location.search);

// 다른 사이트로 보내지 않도록 같은 사이트 안의 주소만 받는다 (/\evil.com 같은 것도 브라우저는 다른 사이트로 읽는다)
const next = safeNext(params.get('next'));

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// ----- 탭 -----
function showTab(name) {
  tabs.forEach((tab) => {
    const selected = tab.dataset.tab === name;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  loginForm.hidden = name !== 'login';
  signupForm.hidden = name !== 'signup';
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

// 소셜 로그인은 끝나면 next 로 돌아온다
document.getElementById('social-login').hidden = !SOCIAL_LOGIN_READY;
document.querySelectorAll('.social-link').forEach((link) => {
  link.href = `/accounts/${link.dataset.provider}/login/?next=${encodeURIComponent(next)}`;
});

// ----- 폼 -----
function showError(form, message) {
  form.querySelector('.form-error').textContent = message;
}

function suspendedMessage({ reason, ends_at: endsAt }) {
  const until = endsAt ? `${formatDateTime(endsAt)}까지` : '기한 없음';
  return `이용이 제한된 계정이에요 (${until}). 사유: ${reason}`;
}

// 성공하면 onSuccess, 실패하면 서버가 준 문장을 보여 준다
async function submitWith(form, action, onSuccess) {
  const button = form.querySelector('.form-submit');
  showError(form, '');
  button.disabled = true;
  try {
    const result = await action();
    if (result.ok) {
      onSuccess();
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

signupForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const { nickname, email, password, passwordConfirm, agreeTerms, agreePrivacy, over14 } = signupForm.elements;
  const name = nickname.value.trim();

  if (name.length < 2 || name.length > 20) return showError(signupForm, '닉네임은 2~20자로 입력해 주세요.');
  if (!EMAIL_PATTERN.test(email.value.trim())) return showError(signupForm, '이메일을 올바르게 입력해 주세요.');
  if (password.value.length < 8) return showError(signupForm, '비밀번호는 8자 이상이어야 해요.');
  if (password.value !== passwordConfirm.value) return showError(signupForm, '비밀번호 확인이 맞지 않아요.');
  if (!agreeTerms.checked || !agreePrivacy.checked || !over14.checked) {
    return showError(signupForm, '필수 항목에 모두 동의해 주세요.');
  }

  submitWith(signupForm, () => Auth.signUp({
    nickname: name,
    email: email.value,
    password: password.value,
    agreeTerms: agreeTerms.checked,
    agreePrivacy: agreePrivacy.checked,
    over14: over14.checked,
  }), () => showVerificationSent(email.value.trim()));
});

// 이미 로그인했으면 돌아갈 곳으로 보낸다
Auth.currentUser().then((user) => {
  if (user) location.replace(next);
});
if (params.get('tab') === 'signup') showTab('signup');
if (params.get('verified') === '1') document.getElementById('verified-done').hidden = false;
// 인증 링크가 만료돼 넘어온 경우 (verify-email 화면)
if (params.get('resend') === '1') showResend();
