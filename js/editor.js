/**
 * WYSIWYG 에디터
 * contenteditable 영역 + 툴바 버튼으로 서식을 넣는다.
 *
 * 사용법:
 *   const editor = createEditor(document.getElementById('editor'), document.getElementById('toolbar'), {
 *     uploadImage: async (file) => '올린 사진 주소',   // 사진을 서버에 올리고 주소를 돌려준다
 *   });
 *   editor.getHTML();          // 본문 HTML 꺼내기
 *   editor.setHTML('<p>..</p>');
 */
function createEditor(area, toolbar, options = {}) {
  let savedRange = null;

  area.contentEditable = 'true';
  document.execCommand('defaultParagraphSeparator', false, 'p');
  document.execCommand('styleWithCSS', false, true); // 글자색 등을 <font> 대신 style로

  // ----- 선택 영역 기억하기 -----
  // 색상 선택창이나 드롭다운을 누르면 에디터의 선택이 풀리므로 미리 저장해 두었다가 되살린다
  function saveSelection() {
    const sel = window.getSelection();
    if (sel.rangeCount && area.contains(sel.anchorNode)) {
      savedRange = sel.getRangeAt(0).cloneRange();
    }
  }

  function restoreSelection() {
    area.focus();
    if (!savedRange) return;
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(savedRange);
  }

  function run(command, value) {
    restoreSelection();
    document.execCommand(command, false, value);
    saveSelection();
    updateToolbar();
    updateEmptyState();
  }

  // ----- 툴바 상태 (현재 커서 위치가 굵게인지 등) -----
  const stateCommands = ['bold', 'italic', 'underline', 'strikeThrough', 'insertUnorderedList', 'insertOrderedList', 'justifyLeft', 'justifyCenter', 'justifyRight'];
  const blockSelect = toolbar.querySelector('[data-block]');

  function updateToolbar() {
    stateCommands.forEach((cmd) => {
      const btn = toolbar.querySelector(`[data-command="${cmd}"]`);
      if (btn) btn.classList.toggle('is-active', document.queryCommandState(cmd));
    });
    const block = String(document.queryCommandValue('formatBlock')).toLowerCase().replace(/[<>]/g, '');
    if (blockSelect) {
      blockSelect.value = ['h2', 'h3'].includes(block) ? block : 'p';
    }
  }

  // 비어 있으면 안내 문구를 보여 주기 위한 클래스
  function updateEmptyState() {
    const empty = !area.textContent.trim() && !area.querySelector('img, hr');
    area.classList.toggle('is-empty', empty);
  }

  // ----- 이미지 넣기 -----
  const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
  const IMAGE_MAX_BYTES = 10 * 1024 * 1024; // 서버 업로드 상한과 같게 (ERD REQ-004)

  async function insertImageFile(file) {
    if (!IMAGE_TYPES.includes(file.type)) {
      alert('jpg · png · gif · webp 사진만 넣을 수 있어요.');
      return;
    }
    if (file.size > IMAGE_MAX_BYTES) {
      alert('10MB 이하 사진만 넣을 수 있어요.');
      return;
    }
    try {
      const url = await options.uploadImage(file);
      run('insertImage', url);
    } catch (e) {
      alert(e.message || '사진을 올리지 못했어요.');
    }
  }

  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = IMAGE_TYPES.join(', ');
  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    fileInput.value = '';
    if (file) insertImageFile(file);
  });

  // 정렬 버튼 하나로 왼쪽 → 가운데 → 오른쪽을 돌아가며 바꾼다
  function cycleAlign() {
    restoreSelection();
    const order = ['justifyLeft', 'justifyCenter', 'justifyRight'];
    const current = order.findIndex((cmd) => document.queryCommandState(cmd));
    run(order[(current + 1) % order.length]);
  }

  function insertLink() {
    const url = prompt('링크 주소를 입력하세요', 'https://');
    if (!url || url === 'https://') return;
    if (!/^(https?:|mailto:)/i.test(url)) {
      alert('http:// 또는 https:// 로 시작하는 주소만 넣을 수 있습니다.');
      return;
    }
    // prompt 창이 뜨면 선택이 풀리므로 저장해 둔 선택 영역으로 판단한다
    if (!savedRange || savedRange.collapsed) {
      // 선택한 글자가 없으면 주소 자체를 링크 글자로 넣는다
      const a = document.createElement('a');
      a.href = url;
      a.textContent = url;
      run('insertHTML', a.outerHTML);
    } else {
      run('createLink', url);
    }
  }

  // ----- 툴바 이벤트 -----
  // 버튼을 눌러도 에디터의 선택(파란 영역)이 풀리지 않게 한다
  toolbar.addEventListener('mousedown', (e) => {
    if (e.target.closest('button')) e.preventDefault();
  });

  toolbar.addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;

    const { command, action } = btn.dataset;
    if (command) run(command, btn.dataset.value);
    if (action === 'link') insertLink();
    if (action === 'image') { saveSelection(); fileInput.click(); }
    if (action === 'quote') run('formatBlock', '<blockquote>');
    if (action === 'code') run('formatBlock', '<pre>');
    if (action === 'align') cycleAlign();
  });

  if (blockSelect) {
    blockSelect.addEventListener('change', () => run('formatBlock', `<${blockSelect.value}>`));
  }

  const colorInput = toolbar.querySelector('[data-color]');
  if (colorInput) {
    colorInput.addEventListener('input', () => run('foreColor', colorInput.value));
  }

  // ----- 에디터 이벤트 -----
  document.addEventListener('selectionchange', () => {
    if (area.contains(window.getSelection().anchorNode)) {
      saveSelection();
      updateToolbar();
    }
  });

  area.addEventListener('input', updateEmptyState);

  const imageFiles = (list) => Array.from(list || []).filter((file) => file.type.startsWith('image/'));

  // 붙여넣기
  // - 화면 캡처 · 복사한 사진: 서버에 올려서 넣는다 (그대로 두면 본문에 남지 않는다. 본문 사진은 우리 서버에 올린 것만 받는다)
  // - 다른 사이트에서 복사한 글: 지저분한 서식이 따라오므로 허용한 태그만 남겨 붙인다
  area.addEventListener('paste', async (e) => {
    const html = e.clipboardData.getData('text/html');
    const images = imageFiles(e.clipboardData.files);
    // 글자가 있는 HTML 이면 글이 먼저다. 워드 · 엑셀은 복사한 글을 그림으로도 함께 주므로, 그림을 먼저 보면 글이 사진이 된다
    const hasText = html && htmlToText(html);
    if (images.length && !hasText && options.uploadImage) {
      e.preventDefault();
      saveSelection();
      for (const file of images) {
        await insertImageFile(file);
      }
      return;
    }
    if (!html) return; // 일반 글자는 브라우저 기본 동작대로
    e.preventDefault();
    run('insertHTML', sanitizeHTML(html));
  });

  // 본문에 파일을 끌어다 놓기: 사진이면 놓은 자리에 올려서 넣는다.
  // 막지 않으면 브라우저가 그 파일을 이 창에 열어 쓰던 화면을 떠난다
  const draggingFiles = (e) => Array.from((e.dataTransfer && e.dataTransfer.types) || []).includes('Files');

  function rangeAt(x, y) {
    if (document.caretRangeFromPoint) return document.caretRangeFromPoint(x, y);
    if (document.caretPositionFromPoint) {
      const position = document.caretPositionFromPoint(x, y);
      if (!position) return null;
      const range = document.createRange();
      range.setStart(position.offsetNode, position.offset);
      range.collapse(true);
      return range;
    }
    return null;
  }

  area.addEventListener('dragover', (e) => {
    if (draggingFiles(e)) e.preventDefault();
  });

  area.addEventListener('drop', async (e) => {
    if (!draggingFiles(e)) return; // 본문 안에서 글자 · 사진을 옮기는 것은 브라우저 기본 동작대로
    e.preventDefault();
    if (!options.uploadImage) return;
    const range = rangeAt(e.clientX, e.clientY);
    if (range && area.contains(range.startContainer)) savedRange = range;
    for (const file of Array.from(e.dataTransfer.files)) {
      await insertImageFile(file); // 사진이 아니면 안내만 하고 넘어간다
    }
  });

  // 비어 있을 때 첫 줄이 <p>로 시작하도록
  function ensureParagraph() {
    if (!area.innerHTML.trim()) area.innerHTML = '<p><br></p>';
  }

  ensureParagraph();
  updateEmptyState();

  return {
    getHTML() {
      return sanitizeHTML(area.innerHTML);
    },
    setHTML(html) {
      area.innerHTML = sanitizeHTML(html);
      ensureParagraph();
      updateEmptyState();
    },
    isEmpty() {
      return area.classList.contains('is-empty');
    },
    focus() {
      area.focus();
    },
    // 커서 자리(없으면 맨 끝)에 사진 넣기
    insertImageFile(file) {
      if (!savedRange) {
        area.focus();
        const range = document.createRange();
        range.selectNodeContents(area);
        range.collapse(false);
        savedRange = range;
      }
      return insertImageFile(file);
    },
    // 본문에 들어 있는 사진 주소들
    getImages() {
      return Array.from(area.querySelectorAll('img'), (img) => img.getAttribute('src'));
    },
    onChange(callback) {
      area.addEventListener('input', callback);
      new MutationObserver(callback).observe(area, { childList: true, subtree: true });
    },
  };
}
