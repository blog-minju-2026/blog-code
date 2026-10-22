/**
 * 한채 짓기 (SCR-13)
 * 로그인하지 않았으면 로그인으로, 이미 한채가 있으면 내 마당으로 보낸다.
 */
const form = document.getElementById('build-form');
const addressInput = document.getElementById('address');
const nameInput = document.getElementById('name');
const introInput = document.getElementById('intro');
const addressStatus = document.getElementById('address-status');
const errorBox = document.getElementById('form-error');

const CHECK_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>';

let nickname = '';
let addressOk = false;

// ----- 주소 확인: 입력이 멈추면 쓸 수 있는지 본다 -----
let checkTimer = null;
async function checkAddress() {
  const address = addressInput.value;
  if (!address) {
    addressOk = false;
    addressStatus.className = 'address-status';
    addressStatus.textContent = '';
    return;
  }
  let result;
  try {
    result = await Store.checkAddress(address);
  } catch (err) {
    result = { available: false, reason: err.message };
  }
  if (address !== addressInput.value) return; // 그새 바뀌었으면 버린다
  addressOk = result.available;
  addressStatus.className = `address-status ${result.available ? 'is-ok' : 'is-bad'}`;
  addressStatus.innerHTML = result.available ? `${CHECK_ICON}쓸 수 있는 주소예요` : escapeHTML(result.reason);
}

addressInput.addEventListener('input', () => {
  // 대문자는 소문자로 바꿔 준다
  const lower = addressInput.value.toLowerCase();
  if (lower !== addressInput.value) addressInput.value = lower;
  addressOk = false;
  clearTimeout(checkTimer);
  checkTimer = setTimeout(checkAddress, 300);
  renderPreview();
});

// ----- 미리보기 -----
function renderPreview() {
  document.getElementById('preview-name').textContent = nameInput.value.trim() || '한채 이름';
  document.getElementById('preview-nickname').textContent = nickname;
  document.getElementById('preview-intro').textContent = introInput.value.trim() || '주인 소개가 여기에 보여요';
  document.getElementById('intro-count').textContent = `${introInput.value.length} / 200`;
}

nameInput.addEventListener('input', renderPreview);
introInput.addEventListener('input', renderPreview);

// ----- 짓기 -----
// 주소 확인을 기다리는 동안 한 번 더 눌러도 두 번 보내지 않는다. 지으면 마당으로 넘어가므로 막아 둔 채 둔다
let building = false;
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (building) return;
  building = true;
  building = await build().catch(() => false);
});

// 지었으면 true
async function build() {
  errorBox.textContent = '';

  clearTimeout(checkTimer);
  await checkAddress();
  const name = nameInput.value.trim();
  if (!addressOk) {
    errorBox.textContent = addressInput.value ? '한채 주소를 다시 확인해 주세요.' : '한채 주소를 입력해 주세요.';
    addressInput.focus();
    return false;
  }
  if (!name || name.length > 40) {
    errorBox.textContent = '한채 이름을 1~40자로 입력해 주세요.';
    nameInput.focus();
    return false;
  }

  const button = document.getElementById('build-submit');
  button.disabled = true;
  try {
    const blog = await Store.createBlog({
      address: addressInput.value,
      name,
      description: introInput.value.trim(),
    });
    location.href = Links.yard(blog.address);
    return true;
  } catch (err) {
    // 칸별 오류(fields)가 오면 그 칸의 문장을 먼저 보여 준다
    errorBox.textContent = err.firstMessage || err.message;
    if (err.fields && err.fields.address) {
      addressStatus.className = 'address-status is-bad';
      addressStatus.textContent = err.fields.address;
      addressInput.focus();
    }
    button.disabled = false;
    return false;
  }
}

async function main() {
  const user = await Auth.currentUser();
  if (!user) {
    location.replace(Links.login(Links.here()));
    return;
  }
  if (user.blog_address) {
    location.replace(Links.yard(user.blog_address));
    return;
  }

  nickname = user.nickname;
  nameInput.value = `${nickname}의 한채`;
  renderPreview();
  document.getElementById('build').hidden = false;
  addressInput.focus();
}

runPage(main);
