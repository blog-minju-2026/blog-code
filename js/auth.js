/**
 * 회원가입 · 로그인 (API 명세서 4.1)
 * 서버의 /api/auth/* 를 부른다. 로그인 상태는 Django 세션 쿠키로 유지된다.
 *
 * 로그인한 사용자: { nickname, email, profile_image_url, role, blog_address }
 * blog_address 가 null 이면 아직 한채가 없는 회원이다.
 */
const Auth = (function () {
  let mePromise = null;

  // 한 화면에서 여러 번 불러도 서버에는 한 번만 묻는다. 비회원이면 null.
  // 서버 오류 · 연결 끊김은 '로그인 안 함'과 다르므로 ApiError 로 실패한다
  // (로그인한 사람이 잠깐의 오류로 로그인 화면에 튕기지 않게). 실패했으면 다음에 다시 묻는다.
  function currentUser() {
    if (!mePromise) {
      mePromise = Api.get('/api/auth/me')
        .then((data) => data.user)
        .catch((err) => {
          // 이용 제한: 서버가 세션을 끊었다. 사유 · 기한을 한 번 알리고 비회원으로 이어 간다
          if (err.code === 'SUSPENDED') {
            alert(suspendedMessage(err.detail || {}));
            return null;
          }
          mePromise = null;
          throw err;
        });
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

  // 로그아웃. 세션이 이미 끝났으면(401 · 이용 제한) 로그아웃된 것으로 본다. 그 밖의 실패는 ApiError
  async function logOut() {
    try {
      await Api.post('/api/auth/logout');
    } catch (err) {
      if (err.status !== 401 && err.code !== 'SUSPENDED') throw err;
    }
    mePromise = Promise.resolve(null);
  }

  // 메일의 인증 키와 가입할 때 정한 비밀번호로 이메일 인증을 마친다. 맞으면 바로 로그인된다.
  // 돌려주는 값: 로그인한 사용자 (이용 제한 중이면 null). 실패하면 ApiError
  async function verifyEmail(key, password) {
    const data = await Api.post('/api/auth/email/verify', { key, password });
    mePromise = Promise.resolve(data.user);
    return data.user;
  }

  // 비밀번호를 새로 정하는 링크를 메일로 받는다. 돌려주는 값: { ok: true } 또는 { ok: false, message }
  async function requestPasswordReset(email) {
    try {
      await Api.post('/api/auth/password/reset', { email: email.trim() });
      return { ok: true };
    } catch (err) {
      return { ok: false, message: err.firstMessage || err.message };
    }
  }

  // 메일 링크의 uid · token 으로 새 비밀번호를 정한다. 실패하면 ApiError
  async function resetPassword(uid, token, password) {
    await Api.post('/api/auth/password/reset/confirm', { uid, token, password });
  }

  // 인증 메일 다시 보내기. 실패하면 ApiError (1분 안에 또 보내면 429)
  async function resendVerification(email) {
    await Api.post('/api/auth/email/resend', { email });
  }

  // ----- 소셜 로그인 (AUTH-03) -----
  // 켜진 제공사와, 제공사에서 막 돌아온 사람의 다음 할 일: { providers, signup, blocked }
  // signup: 처음 온 사람의 { provider, provider_name, email, nickname } · blocked: 이용 제한 { reason, ends_at }
  function socialStatus() {
    return Api.get('/api/auth/social');
  }

  // 제공사 로그인으로 보낸다. 끝나면 next 로 돌아오고, 처음 온 사람은 /login?social=signup 으로 온다.
  // allauth 는 POST 로 들어와야 제공사로 보내므로 폼을 만들어 제출한다
  async function startSocialLogin(provider, next) {
    const form = document.createElement('form');
    form.method = 'post';
    form.action = `/accounts/${encodeURIComponent(provider)}/login/`;
    const fields = { csrfmiddlewaretoken: await Api.csrfToken(), process: 'login', next };
    Object.entries(fields).forEach(([name, value]) => {
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = name;
      input.value = value;
      form.append(input);
    });
    document.body.append(form);
    form.submit();
  }

  // 소셜 계정으로 처음 온 사람의 가입을 마친다. 마치면 바로 로그인된다.
  // 돌려주는 값: { ok: true, next } 또는 { ok: false, code, message, fields }
  async function finishSocialSignup({ nickname, agreeTerms, agreePrivacy, over14 }) {
    try {
      const data = await Api.post('/api/auth/social/signup', {
        nickname: nickname.trim(),
        agree_terms: agreeTerms,
        agree_privacy: agreePrivacy,
        over_14: over14,
      });
      mePromise = Promise.resolve(data.user);
      return { ok: true, next: data.next };
    } catch (err) {
      return { ok: false, code: err.code, message: err.firstMessage || err.message, fields: err.fields };
    }
  }

  return {
    signUp, logIn, logOut, currentUser, refresh, verifyEmail, resendVerification, requestPasswordReset, resetPassword,
    socialStatus, startSocialLogin, finishSocialSignup,
  };
})();
