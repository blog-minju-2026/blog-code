/**
 * 회원가입 · 로그인 (API 명세서 4.1)
 * 서버의 /api/auth/* 를 부른다. 로그인 상태는 Django 세션 쿠키로 유지된다.
 *
 * 로그인한 사용자: { nickname, email, profile_image_url, role, blog_address }
 * blog_address 가 null 이면 아직 한채가 없는 회원이다.
 */
const Auth = (function () {
  let mePromise = null;

  // 한 화면에서 여러 번 불러도 서버에는 한 번만 묻는다
  function currentUser() {
    if (!mePromise) {
      mePromise = Api.get('/api/auth/me')
        .then((data) => data.user)
        .catch(() => null);
    }
    return mePromise;
  }

  // 로그인 · 한채 짓기처럼 내 정보가 바뀐 뒤 다시 묻게 한다
  function refresh() {
    mePromise = null;
    return currentUser();
  }

  /**
   * 회원가입. 가입하면 인증 메일이 가고, 인증해야 로그인할 수 있다.
   * 돌려주는 값: { ok: true } 또는 { ok: false, message, fields }
   */
  async function signUp({ nickname, email, password, agreeTerms, agreePrivacy, over14 }) {
    try {
      await Api.post('/api/auth/signup', {
        email: email.trim(),
        password,
        nickname: nickname.trim(),
        agree_terms: agreeTerms,
        agree_privacy: agreePrivacy,
        over_14: over14,
      });
      return { ok: true };
    } catch (err) {
      return { ok: false, message: err.firstMessage || err.message, fields: err.fields };
    }
  }

  async function logIn(email, password) {
    try {
      const data = await Api.post('/api/auth/login', { email: email.trim(), password });
      mePromise = Promise.resolve(data.user);
      return { ok: true };
    } catch (err) {
      return { ok: false, code: err.code, message: err.firstMessage || err.message, detail: err.detail };
    }
  }

  async function logOut() {
    try {
      await Api.post('/api/auth/logout');
    } finally {
      mePromise = Promise.resolve(null);
    }
  }

  // 메일의 인증 키로 이메일 인증
  async function verifyEmail(key) {
    await Api.post('/api/auth/email/verify', { key });
  }

  // 인증 메일 다시 보내기. 실패하면 ApiError (1분 안에 또 보내면 429)
  async function resendVerification(email) {
    await Api.post('/api/auth/email/resend', { email });
  }

  return { signUp, logIn, logOut, currentUser, refresh, verifyEmail, resendVerification };
})();
