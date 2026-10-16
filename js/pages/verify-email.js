/**
 * 이메일 인증 (인증 메일의 링크 /verify-email?key=...)
 * 가입할 때 정한 비밀번호까지 맞아야 인증을 마치고, 그대로 로그인된다.
 * 링크만으로 인증하면 남의 이메일로 먼저 가입해 둔 사람의 비밀번호로 계정이 열리기 때문이다.
 * 비밀번호를 모르면 비밀번호 새로 정하기(/login?forgot=1)로 정하면 인증도 함께 마쳐진다.
 */
const key = new URLSearchParams(location.search).get('key') || '';
const title = document.getElementById('verify-title');
const text = document.getElementById('verify-text');
const form = document.getElementById('verify-form');
const link = document.getElementById('verify-link');
const errorBox = form.querySelector('.form-error');

// 링크가 만료됐거나 잘못됐으면 로그인 화면에서 인증 메일을 다시 받게 한다
function showBadLink(message) {
  title.textContent = '인증하지 못했어요';
  text.textContent = `${message} 로그인 화면에서 인증 메일을 다시 받을 수 있어요.`;
  form.hidden = true;
  link.textContent = '인증 메일 다시 받기';
  link.href = '/login?resend=1';
  link.hidden = false;
}

function showDone(user) {
  title.textContent = '이메일 인증을 마쳤어요';
  form.hidden = true;
  if (user) {
    text.textContent = '이제 나의 한채를 지어 보세요.';
    link.textContent = '한채 짓기';
    link.href = '/build';
  } else {
    // 이용 제한 중이면 로그인되지 않는다. 로그인 화면에서 사유를 알린다
    text.textContent = '로그인 화면에서 로그인해 주세요.';
    link.href = '/login?verified=1';
  }
  link.hidden = false;
}

if (!key) showBadLink('인증 링크가 잘못됐어요.');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const password = form.elements.password.value;
  if (!password) {
    errorBox.textContent = '비밀번호를 입력해 주세요.';
    return;
  }
  const button = form.querySelector('.form-submit');
  errorBox.textContent = '';
  button.disabled = true;
  try {
    showDone(await Auth.verifyEmail(key, password));
  } catch (err) {
    if (err.fields.key) showBadLink(err.message);
    else errorBox.textContent = err.firstMessage || err.message;
  } finally {
    button.disabled = false;
  }
});
