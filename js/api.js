/**
 * 서버 API 부르기 (API 명세서 2장)
 *
 * - 화면과 API 가 같은 주소에 있으므로 세션 쿠키가 그대로 따라간다.
 * - 바꾸는 요청(POST · PATCH · PUT · DELETE)에는 X-CSRFToken 헤더를 붙인다.
 *   csrftoken 쿠키가 없으면 GET /api/auth/csrf 로 먼저 받는다.
 * - 실패하면 ApiError(status, code, message, fields, detail) 를 던진다.
 *
 * 사용법:
 *   const topics = await Api.get('/api/topics');
 *   await Api.post('/api/auth/login', { email, password });
 */
class ApiError extends Error {
  constructor(status, code, message, fields, detail) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields || {};
    this.detail = detail || null; // 예: SUSPENDED 의 { reason, ends_at }
  }

  // 칸별 오류가 있으면 첫 번째 것을, 없으면 전체 메시지
  get firstMessage() {
    const first = Object.values(this.fields)[0];
    return typeof first === 'string' ? first : this.message;
  }
}

const Api = (function () {
  const SAFE_METHODS = ['GET', 'HEAD'];

  function readCookie(name) {
    const found = document.cookie.split('; ').find((part) => part.startsWith(`${name}=`));
    return found ? decodeURIComponent(found.slice(name.length + 1)) : '';
  }

  async function csrfToken() {
    let token = readCookie('csrftoken');
    if (!token) {
      await fetch('/api/auth/csrf', { credentials: 'same-origin' });
      token = readCookie('csrftoken');
    }
    return token;
  }

  async function request(method, url, body) {
    const headers = { Accept: 'application/json' };
    const options = { method, headers, credentials: 'same-origin' };
    if (body instanceof FormData) {
      options.body = body; // 브라우저가 multipart 경계를 붙인다
    } else if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    if (!SAFE_METHODS.includes(method)) {
      headers['X-CSRFToken'] = await csrfToken();
    }

    let response;
    try {
      response = await fetch(url, options);
    } catch (e) {
      throw new ApiError(0, 'NETWORK_ERROR', '서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.');
    }

    if (response.status === 204) return null;
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const error = (data && data.error) || {};
      throw new ApiError(
        response.status,
        error.code || 'SERVER_ERROR',
        error.message || '잠시 후 다시 시도해 주세요.',
        error.fields,
        error.detail,
      );
    }
    return data;
  }

  return {
    get: (url) => request('GET', url),
    post: (url, body) => request('POST', url, body),
    put: (url, body) => request('PUT', url, body),
    patch: (url, body) => request('PATCH', url, body),
    delete: (url) => request('DELETE', url),
    // 파일 하나를 multipart/form-data 의 file 칸으로 올린다
    upload(url, file) {
      const form = new FormData();
      form.append('file', file);
      return request('POST', url, form);
    },
  };
})();
