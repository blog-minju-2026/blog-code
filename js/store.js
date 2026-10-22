/**
 * 데이터 저장소: 서버 API 를 부르는 얇은 묶음 (API 명세서 4장)
 * 응답 모양은 명세서 그대로 돌려준다. 화면은 이 파일의 함수만 부른다.
 *
 * PostSummary { blog: { address, name }, no, title, excerpt, thumbnail_url, category: { id, name } | null,
 *               topic: { slug, name } | null, published_at, like_count, comment_count, visibility, view_count? }
 */
const Store = (function () {
  const enc = encodeURIComponent;
  const blogUrl = (address) => `/api/blogs/${enc(address)}`;
  const postUrl = (address, no) => `${blogUrl(address)}/posts/${no}`;

  const ADDRESS_REASONS = {
    INVALID: '영문 소문자 · 숫자 · 하이픈으로 4~32자를 써 주세요. 하이픈으로 시작하거나 끝날 수 없어요.',
    RESERVED: '서비스가 쓰는 주소라 쓸 수 없어요.',
    TAKEN: '이미 있거나 예약된 주소예요.',
  };

  // 없거나 볼 수 없으면(404) null
  async function orNull(promise) {
    try {
      return await promise;
    } catch (err) {
      if (err.status === 404) return null;
      throw err;
    }
  }

  function query(params) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') search.set(key, value);
    });
    const text = search.toString();
    return text ? `?${text}` : '';
  }

  // ----- 골목 -----
  let topicsCache = null;
  async function getTopics() {
    if (!topicsCache) topicsCache = await Api.get('/api/topics');
    return topicsCache;
  }

  // ----- 한채 -----
  const getBlog = (address) => (address ? orNull(Api.get(blogUrl(address))) : Promise.resolve(null));

  async function getMyBlog() {
    const user = await Auth.currentUser();
    return user && user.blog_address ? getBlog(user.blog_address) : null;
  }

  async function checkAddress(address) {
    const result = await Api.get(`/api/blogs/address-available${query({ address })}`);
    return result.available
      ? { available: true }
      : { available: false, reason: ADDRESS_REASONS[result.reason] || '쓸 수 없는 주소예요.' };
  }

  async function createBlog({ address, name, description }) {
    const blog = await Api.post('/api/blogs', { address, name, description });
    await Auth.refresh(); // 내 정보의 blog_address 가 생겼다
    return blog;
  }

  // 한채 이름 · 주인 소개 바꾸기 (주인만) → 바뀐 대문 정보
  const updateBlog = (address, data) => Api.patch(blogUrl(address), data);

  // { subscribed, subscriber_count }
  const setNeighbor = (address, on) => (on
    ? Api.put(`${blogUrl(address)}/subscription`)
    : Api.delete(`${blogUrl(address)}/subscription`));

  // ----- 방 · 태그 -----
  // { total_count, rooms: [{ id, name, post_count }], uncategorized_count }
  const getRooms = (address) => Api.get(`${blogUrl(address)}/categories`);
  const addRoom = (address, name) => Api.post(`${blogUrl(address)}/categories`, { name });
  const renameRoom = (address, id, name) => Api.patch(`${blogUrl(address)}/categories/${id}`, { name });
  // → { moved_to_uncategorized }
  const deleteRoom = (address, id) => Api.delete(`${blogUrl(address)}/categories/${id}`);
  const orderRooms = (address, ids) => Api.put(`${blogUrl(address)}/categories/order`, { ids });
  // [{ name, post_count }]
  const getTags = (address) => Api.get(`${blogUrl(address)}/tags`);

  // ----- 기록 목록 -----
  // filter: { category: id | 'none', tag, q, page } → { items, page, size, total, total_pages }
  const listPosts = (address, filter = {}) => Api.get(`${blogUrl(address)}/posts${query(filter)}`);

  // 마을 목록 (커서) → { items, next_cursor }
  const newPosts = ({ cursor, limit } = {}) => Api.get(`/api/home/new-posts${query({ cursor, limit })}`);
  const topicPosts = (slug, { cursor, limit } = {}) => Api.get(`/api/topics/${enc(slug)}/posts${query({ cursor, limit })}`);
  const neighborFeed = ({ cursor, limit } = {}) => Api.get(`/api/me/feed${query({ cursor, limit })}`);
  // 내 이웃 한채 (페이지) — items: BlogSummary + post_count
  const myNeighbors = ({ page, size } = {}) => Api.get(`/api/me/subscriptions${query({ page, size })}`);

  // ----- 마을에서 찾기 · 순위 -----
  const searchPosts = ({ q, sort, page }) => Api.get(`/api/search/posts${query({ q, sort, page })}`);
  const searchBlogs = ({ q, page, size }) => Api.get(`/api/search/blogs${query({ q, page, size })}`);
  const postRanking = (limit) => Api.get(`/api/rankings/posts${query({ limit })}`);
  const blogRanking = (limit) => Api.get(`/api/rankings/blogs${query({ limit })}`);

  // ----- 기록 하나 -----
  const getPost = (address, no) => orNull(Api.get(postUrl(address, no)));
  const addView = (address, no) => Api.post(`${postUrl(address, no)}/views`);

  // 임시저장 (주인만). data 는 savePost 와 같은 칸이고 제목 · 본문이 비어도 된다
  // listDrafts → { items: [{ id, title, excerpt, category, image_count, content_length, updated_at }], total, … }
  const listDrafts = (address, { page, size } = {}) => Api.get(`${blogUrl(address)}/drafts${query({ page, size })}`);
  // getDraft → { id, title, content, category, topic, tags, visibility, cover_image_id, images, updated_at }
  const getDraft = (address, id) => Api.get(`${blogUrl(address)}/drafts/${id}`);
  // 새로 임시저장 · 다시 임시저장 → { id, saved_at }
  const saveDraft = (address, data, id) => (id ? Api.patch(`${blogUrl(address)}/drafts/${id}`, data) : Api.post(`${blogUrl(address)}/drafts`, data));
  const deleteDraft = (address, id) => Api.delete(`${blogUrl(address)}/drafts/${id}`);
  // 임시저장한 기록을 발행 → { no, url }
  const publishDraft = (address, id, data) => Api.post(`${blogUrl(address)}/drafts/${id}/publish`, data);

  // data: { title, content, category_id, topic_slug, tags, visibility, cover_image_id, client_token } → { no, url }
  async function savePost(address, data, no) {
    return no ? Api.patch(postUrl(address, no), data) : Api.post(`${blogUrl(address)}/posts`, data);
  }

  const deletePost = (address, no) => Api.delete(postUrl(address, no));

  // { liked, like_count }
  const setLike = (address, no, on) => (on
    ? Api.put(`${postUrl(address, no)}/like`)
    : Api.delete(`${postUrl(address, no)}/like`));

  // ----- 댓글 -----
  // { items: [Comment], count }
  const getComments = (address, no) => Api.get(`${postUrl(address, no)}/comments`);
  const addComment = (address, no, content, clientToken) => Api.post(`${postUrl(address, no)}/comments`, { content, client_token: clientToken });
  const deleteComment = (id) => Api.delete(`/api/comments/${id}`);
  // 한채 관리 › 댓글 · 방명록 (주인만): { items: [Comment + hidden_reason (+ post: { no, title })], page, total, total_pages }
  const manageComments = (address, { page, size } = {}) => Api.get(`${blogUrl(address)}/manage/comments${query({ page, size })}`);
  const manageGuestbook = (address, { page, size } = {}) => Api.get(`${blogUrl(address)}/manage/guestbook${query({ page, size })}`);

  // 내 댓글 고치기 → 고친 Comment
  const editComment = (id, content) => Api.patch(`/api/comments/${id}`, { content });

  // ----- 방명록 -----
  const getGuestbook = (address, page) => Api.get(`${blogUrl(address)}/guestbook${query({ page })}`);
  const addGuestbook = (address, content, clientToken) => Api.post(`${blogUrl(address)}/guestbook`, { content, client_token: clientToken });
  const editGuestbook = (id, content) => Api.patch(`/api/guestbook/${id}`, { content });
  const deleteGuestbook = (id) => Api.delete(`/api/guestbook/${id}`);

  // ----- 내 정보 -----
  // data: { nickname?, profile_image_id? (null 이면 사진 지우기) } → { user }
  // 탈퇴 확인 창에 보일 것: { can_leave, nickname, confirm_with: 'password'|'nickname', social_provider, blog, post_count,
  // subscriber_count, comment_count, guestbook_count }
  const leaveSummary = () => Api.get('/api/me/leave');

  // 탈퇴하고 로그아웃한다. 실패하면 ApiError (비밀번호 · 닉네임이 틀리면 fields 에)
  async function leave({ password, nickname }) {
    await Api.post('/api/me/leave', { password, nickname, agree: true });
    await Auth.refresh().catch(() => null);
  }

  // 로그인 방법 (AUTH-07): { email, has_password, confirm_with, nickname,
  // providers: [{ provider, name, enabled, connected, connected_at, can_disconnect }] }
  const loginMethods = () => Api.get('/api/me/login-methods');

  // 소셜 계정 연결 시작: 본인 확인을 마치면 서버가 10분 동안 그 제공사를 이어도 된다고 기억한다.
  // 그다음 Auth.startSocialLogin(provider, '/me', 'connect') 로 제공사 로그인에 보낸다. 실패하면 ApiError
  const startSocialConnect = (provider, { password, nickname }) => Api.post('/api/me/social/connect', { provider, password, nickname });

  // 연결 끊기. 돌려주는 값: 바뀐 로그인 방법. 마지막 남은 방법이면 409 LAST_LOGIN_METHOD
  const disconnectSocial = (provider) => Api.delete(`/api/me/social/${encodeURIComponent(provider)}`);

  async function updateMe(data) {
    const result = await Api.patch('/api/me', data);
    await Auth.refresh();
    return result.user;
  }

  // { available, reason: null | 'INVALID' | 'TAKEN' }
  const nicknameAvailable = (nickname) => Api.get(`/api/auth/nickname-available${query({ nickname })}`);

  // ----- 사진 -----
  // { id, url, thumb_url, width, height }
  const uploadImage = (file) => Api.upload('/api/images', file);

  return {
    getTopics,
    getBlog,
    getMyBlog,
    checkAddress,
    createBlog,
    updateBlog,
    setNeighbor,
    getRooms,
    addRoom,
    renameRoom,
    deleteRoom,
    orderRooms,
    getTags,
    listPosts,
    newPosts,
    topicPosts,
    neighborFeed,
    myNeighbors,
    searchPosts,
    searchBlogs,
    postRanking,
    blogRanking,
    getPost,
    addView,
    savePost,
    listDrafts,
    getDraft,
    saveDraft,
    deleteDraft,
    publishDraft,
    deletePost,
    setLike,
    getComments,
    addComment,
    deleteComment,
    editComment,
    manageComments,
    manageGuestbook,
    getGuestbook,
    addGuestbook,
    editGuestbook,
    deleteGuestbook,
    uploadImage,
    updateMe,
    leaveSummary,
    leave,
    loginMethods,
    startSocialConnect,
    disconnectSocial,
    nicknameAvailable,
  };
})();
