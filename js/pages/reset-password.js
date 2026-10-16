/**
 * 새 비밀번호 정하기 (비밀번호 재설정 메일의 링크 /reset-password?uid=...&token=...)
 * 링크는 한 번만 · 1시간 동안 쓸 수 있다. 정하고 나면 로그인 화면으로 보낸다.
 */
const params = new URLSearchParams(location.search);
const uid = params.get('uid') || '';
const token = params.get('token') || '';
const title = document.getElementById('reset-title');
const text = document.getElementById('reset-text');
const form = document.getElementById('reset-form');
const again = document.getElementById('reset-again');
const errorBox = form.querySelector('.form-error');

// 링크가 만료됐거나 이미 썼으면 메일을 다시 받게 한다
function showBadLink(message) {
  title.textContent = '링크를 쓸 수 없어요';
  text.textContent = `${message} 비밀번호 재설정 메일을 다시 받아 주세요.`;
  form.hidden = true;
  again.hidden = false;
}

if (!uid || !token) showBadLink('링크가 잘못됐어요.');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const { password, passwordConfirm } = form.elements;
  if (password.value.length < 8) {
    errorBox.textContent = '비밀번호는 8자 이상이어야 해요.';
    return;
  }
  if (password.value !== passwordConfirm.value) {
    errorBox.textContent = '비밀번호 확인이 맞지 않아요.';
    return;
  }
  const button = form.querySelector('.form-submit');
  errorBox.textContent = '';
  button.disabled = true;
  try {
    await Auth.resetPassword(uid, token, password.value);
    location.replace('/login?reset=1');
  } catch (err) {
    if (err.fields.token) showBadLink(err.message);
    else errorBox.textContent = err.firstMessage || err.message;
  } finally {
    button.disabled = false;
  }
});
