/**
 * 기록 (SCR-09)
 * post?address=minju&no=3
 */
const params = new URLSearchParams(location.search);
const address = params.get('address') || '';
const no = Number(params.get('no'));

// 낙관 글자: 닉네임 앞 두 글자를 위아래로
function nakgwanHTML(nickname) {
  return [...nickname].slice(0, 2).map(escapeHTML).join('<br>');
}

// 탈퇴한 주인은 닉네임이 없다 (API 명세서 3.1 '떠난 사람')
function ownerName(blog) {
  return blog.owner.nickname || '떠난 사람';
}

function renderGate(blog) {
  const link = document.getElementById('blog-link');
  link.href = Links.yard(blog.address);
  link.textContent = blog.name;
  const meta = document.getElementById('gate-meta');
  const paintMeta = (count) => { meta.textContent = `${ownerName(blog)} · 이웃 ${count}`; };
  paintMeta(blog.subscriber_count);

  const actions = document.getElementById('gate-actions');
  actions.innerHTML = blog.is_owner
    ? `<a class="btn btn-secondary" href="${Links.yard(blog.address)}">내 마당</a>`
    : '<button type="button" class="btn" id="neighbor-button"></button>';
  actions.insertAdjacentHTML('beforeend', `<a class="btn btn-secondary" href="${Links.guestbook(blog.address)}">방명록</a>`);
  if (!blog.is_owner) bindNeighborButton(document.getElementById('neighbor-button'), blog, paintMeta);
}

function roomLink(category) {
  return Links.yard(address, { category: category ? category.id : 'none' });
}

function renderArticle(post, blog) {
  document.title = `${post.title} · ${blog.name}`;
  document.getElementById('breadcrumb').innerHTML = `
    <a href="/">마을</a><span aria-hidden="true">›</span>
    <a href="${Links.yard(address)}">${escapeHTML(blog.name)}</a><span aria-hidden="true">›</span>
    <a href="${roomLink(post.category)}">${escapeHTML(roomName(post.category))}</a><span aria-hidden="true">›</span>
    <span aria-current="page">${escapeHTML(post.title)}</span>`;

  const room = document.getElementById('room-link');
  room.href = roomLink(post.category);
  room.textContent = post.category ? `${post.category.name}방에 쌓인 기록` : '마루에 놓인 기록';

  const meta = [formatLongDate(post.published_at), `조회 ${post.view_count}`];
  if (post.topic) meta.push(`골목 ${post.topic.name}`);
  if (post.visibility === 'PRIVATE') meta.push('나만 보기');
  document.getElementById('post-title').textContent = post.title;
  document.getElementById('post-meta').textContent = meta.join(' · ');

  // 관리자가 숨긴 기록: 주인에게만 이 칸이 온다 (ADMIN-03)
  if (post.hidden) {
    const notice = document.getElementById('hidden-notice');
    notice.textContent = `관리자가 숨긴 기록이에요. 다른 사람에게는 보이지 않아요. 사유: ${post.hidden.reason}`;
    notice.hidden = false;
  }

  // 서버가 정제한 본문이지만, 화면에 넣기 전에 한 번 더 거른다
  document.getElementById('post-body').innerHTML = sanitizeHTML(post.content);

  document.getElementById('post-tags').innerHTML = post.tags
    .map((t) => `<a class="tag" href="${Links.yard(address, { tag: t })}">#${escapeHTML(t)}</a>`)
    .join('');

  document.getElementById('owner-name').textContent = ownerName(blog);
  const nakgwan = document.getElementById('nakgwan');
  nakgwan.innerHTML = nakgwanHTML(ownerName(blog));
  nakgwan.setAttribute('aria-label', `낙관 ${ownerName(blog)}`);
}

function renderLike(liked, count) {
  document.getElementById('like-button').setAttribute('aria-pressed', String(liked));
  document.getElementById('like-label').textContent = `공감 ${count}`;
}

function bindActions(post) {
  let liked = post.liked_by_me;
  renderLike(liked, post.like_count);

  const likeButton = document.getElementById('like-button');
  if (post.is_owner) {
    // 내 기록에는 공감할 수 없다 (API 명세서 4.6)
    likeButton.disabled = true;
    likeButton.title = '내 기록에는 공감할 수 없어요';
  }
  likeButton.addEventListener('click', async () => {
    try {
      if (!(await Auth.currentUser())) {
        location.href = Links.login(Links.here());
        return;
      }
      const result = await Store.setLike(address, no, !liked);
      liked = result.liked;
      renderLike(liked, result.like_count);
    } catch (err) {
      alert(err.message);
    }
  });

  document.getElementById('copy-button').addEventListener('click', async (e) => {
    try {
      await navigator.clipboard.writeText(location.href);
      e.target.textContent = '복사했어요';
    } catch (err) {
      prompt('이 주소를 복사하세요', location.href);
    }
  });

  if (!post.is_owner) return;
  document.getElementById('owner-tools').hidden = false;
  document.getElementById('edit-link').href = Links.write(no);
  document.getElementById('delete-button').addEventListener('click', async () => {
    const ok = await confirmDialog({
      title: '이 기록을 삭제할까요?',
      text: `‘${post.title}’의 댓글과 공감도 함께 사라지고, 되돌릴 수 없어요.`,
      confirmLabel: '삭제',
      danger: true,
    });
    if (!ok) return;
    try {
      await Store.deletePost(address, no);
      location.href = Links.yard(address);
    } catch (err) {
      alert(err.message);
    }
  });
}

function renderNav(post) {
  const nav = document.getElementById('post-nav');
  const { prev, next } = post;
  if (!prev && !next) {
    nav.hidden = true;
    return;
  }
  nav.innerHTML = (prev
    ? `<a class="card" href="${Links.post(address, prev.no)}"><span class="post-nav-label">‹ 이전 기록</span><span class="post-nav-title">${escapeHTML(prev.title)}</span></a>`
    : '') + (next
    ? `<a class="card next" href="${Links.post(address, next.no)}"><span class="post-nav-label">다음 기록 ›</span><span class="post-nav-title">${escapeHTML(next.title)}</span></a>`
    : '');
}

// ----- 댓글 -----
function commentHTML(c) {
  const name = c.author.withdrawn ? '떠난 사람' : escapeHTML(c.author.nickname);
  const authorLink = c.author.blog_address
    ? `<a class="comment-name" href="${Links.yard(c.author.blog_address)}">${name}</a>`
    : `<span class="comment-name">${name}</span>`;
  const text = c.hidden ? '<em class="comment-hidden">관리자가 숨긴 댓글이에요.</em>' : escapeHTML(c.content);
  const edited = c.edited_at ? ' · 고침' : '';
  const remove = c.can_delete ? `<button type="button" class="comment-delete" data-delete="${c.id}">삭제</button>` : '';
  return `
    <li class="comment">
      ${avatarHTML(c.author.profile_image_url, 'comment-avatar')}
      <div class="comment-body">
        <div class="comment-head">
          ${authorLink}
          <span class="comment-when">${formatDateTime(c.created_at)}${edited}</span>
          ${remove}
        </div>
        <p class="comment-text">${text}</p>
      </div>
    </li>`;
}

async function loadComments() {
  const { items, count } = await Store.getComments(address, no);
  document.getElementById('comments-title').textContent = `댓글 ${count}`;
  document.getElementById('comment-list').innerHTML = items.map(commentHTML).join('');
}

document.getElementById('comment-list').addEventListener('click', async (e) => {
  const button = e.target.closest('[data-delete]');
  if (!button) return;
  const ok = await confirmDialog({ title: '이 댓글을 지울까요?', text: '지운 댓글은 되돌릴 수 없어요.', confirmLabel: '삭제', danger: true });
  if (!ok) return;
  try {
    await Store.deleteComment(button.dataset.delete);
    await loadComments();
  } catch (err) {
    alert(err.message);
  }
});

function bindCommentForm(user) {
  const form = document.getElementById('comment-form');
  if (!user) {
    form.innerHTML = `<p class="comment-login"><a class="text-link" href="${Links.login(Links.here())}">로그인</a>하면 댓글을 남길 수 있어요.</p>`;
    return;
  }
  const text = document.getElementById('comment-text');
  const count = document.getElementById('comment-count');
  const button = form.querySelector('button[type="submit"]');
  let clientToken = newClientToken();

  text.addEventListener('input', () => {
    count.textContent = `${text.value.length.toLocaleString()} / 1,000`;
  });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const value = text.value.trim();
    if (!value) {
      text.focus();
      return;
    }
    button.disabled = true;
    try {
      await Store.addComment(address, no, value, clientToken);
      clientToken = newClientToken(); // 다음 댓글은 새 토큰으로
      text.value = '';
      count.textContent = '0 / 1,000';
      await loadComments();
    } catch (err) {
      alert(err.firstMessage || err.message);
    } finally {
      button.disabled = false;
    }
  });
}

// ----- 사이드바 -----
async function renderSide(post) {
  const rooms = await Store.getRooms(address);
  const item = (label, count, href, current) => `
    <li><a href="${href}"${current ? ' aria-current="page"' : ''}>
      <span class="name">${escapeHTML(label)}</span><span class="count">${count}</span>
    </a></li>`;
  const currentId = post.category ? post.category.id : null;
  const list = [
    item('모든 기록', rooms.total_count, Links.yard(address), false),
    ...rooms.rooms.map((r) => item(r.name, r.post_count, roomLink(r), r.id === currentId)),
  ];
  if (rooms.uncategorized_count) list.push(item('마루', rooms.uncategorized_count, roomLink(null), currentId === null));
  document.getElementById('room-list').innerHTML = list.join('');

  const same = (await Store.listPosts(address, { category: currentId || 'none', size: 6 })).items
    .filter((p) => p.no !== no)
    .slice(0, 5);
  if (same.length) {
    document.getElementById('same-room').hidden = false;
    document.getElementById('same-room-title').textContent = post.category ? `${post.category.name}방의 다른 기록` : '마루의 다른 기록';
    document.getElementById('same-room-list').innerHTML = same
      .map((p) => `<li><a href="${Links.post(address, p.no)}">${escapeHTML(p.title)}</a></li>`)
      .join('');
  }
}

async function main() {
  bindVillageSearch(document.getElementById('village-search'));
  const { user } = await renderHeaderNav(document.getElementById('header-nav'));

  const [blog, post] = await Promise.all([Store.getBlog(address), Store.getPost(address, no)]);
  if (!blog || !post) {
    showLost('notFound');
    return;
  }

  // 조회는 따로 알린다. 같은 사람이 30분 안에 다시 열면 서버가 세지 않는다
  Store.addView(address, no).catch(() => {});

  renderGate(blog);
  renderArticle(post, blog);
  bindActions(post);
  renderNav(post);
  bindCommentForm(user);
  await Promise.all([loadComments(), renderSide(post)]);

  document.getElementById('gate').hidden = false;
  document.getElementById('house').hidden = false;
}

runPage(main);
