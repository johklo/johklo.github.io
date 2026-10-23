const PAGE_URL = 'https://api.github.com/repos/johklo/johklo.github.io/contents/content/docs/book/_index.md';
const BRANCH = 'master';

export function validateBooks(value) {
  if (!Array.isArray(value)) throw new Error('독서 목록 형식이 올바르지 않습니다.');
  const ids = new Set();
  return value.map(book => {
    if (!book || typeof book !== 'object' ||
        typeof book.id !== 'string' || !/^[a-zA-Z0-9_-]+$/.test(book.id) ||
        ids.has(book.id) || typeof book.title !== 'string' ||
        !book.title.trim() || typeof book.read !== 'boolean') {
      throw new Error('독서 목록의 제목, 식별자 또는 읽음 상태를 확인해 주세요.');
    }
    ids.add(book.id);
    return { id: book.id, title: book.title.trim(), read: book.read };
  });
}

export function parsePage(source) {
  const start = source.search(/\S/);
  if (source[start] !== '{') throw new Error('Book 페이지의 JSON 머리말을 찾을 수 없습니다.');
  let depth = 0;
  let quoted = false;
  let escaped = false;
  for (let index = start; index < source.length; index++) {
    const character = source[index];
    if (quoted) {
      if (escaped) escaped = false;
      else if (character === '\\') escaped = true;
      else if (character === '"') quoted = false;
    } else if (character === '"') {
      quoted = true;
    } else if (character === '{') {
      depth++;
    } else if (character === '}' && --depth === 0) {
      let metadata;
      try {
        metadata = JSON.parse(source.slice(start, index + 1));
      } catch (error) {
        throw new Error('Book 페이지의 JSON 머리말이 올바르지 않습니다.', { cause: error });
      }
      return {
        metadata,
        books: validateBooks(metadata.reading_list),
        leading: source.slice(0, start),
        body: source.slice(index + 1)
      };
    }
  }
  throw new Error('Book 페이지 머리말의 끝을 찾을 수 없습니다.');
}

export function updatePage(source, books) {
  const page = parsePage(source);
  const newline = source.includes('\r\n') ? '\r\n' : '\n';
  const metadata = { ...page.metadata, reading_list: validateBooks(books) };
  return page.leading + JSON.stringify(metadata, null, 2).replaceAll('\n', newline) + page.body;
}

export function encodeContent(text) {
  const bytes = new TextEncoder().encode(text);
  return btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(''));
}

export function decodeContent(text) {
  return new TextDecoder('utf-8', { fatal: true }).decode(
    Uint8Array.from(atob(text.replace(/\s/g, '')), character => character.charCodeAt(0))
  );
}

function sameBooks(left, right) {
  return JSON.stringify(validateBooks(left)) === JSON.stringify(validateBooks(right));
}

async function request(url, token, options, fetcher) {
  const headers = {
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28'
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body) headers['Content-Type'] = 'application/json';
  const response = await fetcher(url, {
    ...options, headers, cache: 'no-store', signal: AbortSignal.timeout(15000)
  });
  if (!response.ok) {
    const messages = {
      401: 'GitHub 토큰을 확인해 주세요.',
      403: '저장소 접근 권한이나 GitHub API 사용 한도를 확인해 주세요.',
      404: 'Book 페이지를 찾을 수 없습니다. 저장소와 토큰 접근 범위를 확인해 주세요.',
      409: '다른 변경이 먼저 저장됐습니다. 최신 목록을 다시 불러와 주세요.',
      422: 'GitHub에서 저장을 거절했습니다. 브랜치 보호 정책과 페이지 상태를 확인해 주세요.'
    };
    throw new Error(messages[response.status] || `GitHub 요청에 실패했습니다. HTTP ${response.status}`);
  }
  return response.json();
}

export async function loadPage(token = '', fetcher = fetch) {
  const data = await request(`${PAGE_URL}?ref=${BRANCH}`, token, {}, fetcher);
  if (data.encoding !== 'base64' || typeof data.content !== 'string' ||
      typeof data.sha !== 'string' || !data.sha) {
    throw new Error('GitHub에서 올바른 페이지 파일을 받지 못했습니다.');
  }
  const source = decodeContent(data.content);
  return { source, sha: data.sha, books: parsePage(source).books };
}

export async function savePage(token, baseBooks, books, fetcher = fetch) {
  if (!token.trim()) throw new Error('저장하려면 GitHub 저장 설정에 토큰을 입력해 주세요.');
  const latest = await loadPage(token.trim(), fetcher);
  if (!sameBooks(latest.books, baseBooks)) {
    throw new Error('다른 기기에서 독서 목록이 변경됐습니다. 최신 목록을 다시 불러온 뒤 수정해 주세요.');
  }
  const nextBooks = validateBooks(books);
  const result = await request(PAGE_URL, token.trim(), {
    method: 'PUT',
    body: JSON.stringify({
      branch: BRANCH,
      sha: latest.sha,
      message: 'docs: update reading list',
      content: encodeContent(updatePage(latest.source, nextBooks))
    })
  }, fetcher);
  if (!result.commit || typeof result.commit.sha !== 'string') {
    throw new Error('GitHub 저장 결과를 확인할 수 없습니다. 다시 불러와 저장 상태를 확인해 주세요.');
  }
  return nextBooks;
}

export function mountReadingList(root) {
  const controls = root.querySelector('[data-reading-controls]');
  const list = root.querySelector('[data-reading-books]');
  const counter = root.querySelector('[data-reading-count]');
  const status = root.querySelector('[data-reading-status]');
  const tokenInput = root.querySelector('[data-reading-token]');
  const saveButton = root.querySelector('[data-reading-save]');
  const reloadButton = root.querySelector('[data-reading-reload]');
  let books;
  try {
    books = validateBooks(JSON.parse(root.querySelector('[data-reading-state]').textContent));
  } catch (error) {
    status.setAttribute('role', 'alert');
    status.textContent = `목록을 열 수 없습니다. ${error.message}`;
    return;
  }
  let baseBooks = books;
  let busy = false;
  const dirty = () => !sameBooks(books, baseBooks);

  function notify(message, error = false) {
    status.setAttribute('role', error ? 'alert' : 'status');
    status.textContent = message;
  }

  function setBusy(value) {
    busy = value;
    controls.disabled = value;
    root.setAttribute('aria-busy', String(value));
    saveButton.disabled = value || !dirty();
  }

  function render() {
    const focusedId = document.activeElement?.id;
    list.replaceChildren();
    for (const book of books) {
      const item = document.createElement('li');
      const label = document.createElement('label');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.id = `${root.id}-book-${book.id}`;
      checkbox.checked = book.read;
      const title = document.createElement('span');
      title.textContent = book.title;
      label.append(checkbox, title);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.id = `${root.id}-remove-${book.id}`;
      remove.textContent = '삭제';
      remove.setAttribute('aria-label', `${book.title} 삭제`);
      checkbox.addEventListener('change', () => {
        books = books.map(value => value.id === book.id ? { ...value, read: checkbox.checked } : value);
        render();
        notify(dirty() ? '저장하지 않은 변경이 있습니다.' : '저장된 목록과 같습니다.');
      });
      remove.addEventListener('click', () => {
        if (!window.confirm(`"${book.title}"을 목록에서 삭제할까요?`)) return;
        books = books.filter(value => value.id !== book.id);
        render();
        reloadButton.focus();
        notify('저장하지 않은 변경이 있습니다.');
      });
      item.append(label, remove);
      list.append(item);
    }
    counter.textContent = `읽은 책 ${books.filter(book => book.read).length} / ${books.length}`;
    if (!books.length) {
      const empty = document.createElement('li');
      empty.textContent = '등록한 책이 없습니다.';
      list.append(empty);
    }
    saveButton.disabled = busy || !dirty();
    if (focusedId) document.getElementById(focusedId)?.focus();
  }

  async function reload(confirmDiscard) {
    if (confirmDiscard && dirty() && !window.confirm('저장하지 않은 변경을 버리고 다시 불러올까요?')) return;
    setBusy(true);
    notify('GitHub에서 목록을 불러오는 중입니다.');
    try {
      const page = await loadPage(tokenInput.value.trim());
      books = page.books;
      baseBooks = books;
      render();
      notify('최신 목록을 불러왔습니다.');
    } catch (error) {
      notify(`최신 목록을 불러오지 못했습니다. ${error.message} 현재 표시된 목록은 유지됩니다.`, true);
    } finally {
      tokenInput.value = '';
      setBusy(false);
    }
  }

  saveButton.addEventListener('click', async () => {
    if (busy || !dirty()) return;
    const token = tokenInput.value.trim();
    if (!token) {
      root.querySelector('details').open = true;
      notify('저장하려면 GitHub 저장 설정에 토큰을 입력해 주세요.', true);
      tokenInput.focus();
      return;
    }
    setBusy(true);
    notify('GitHub에 저장하는 중입니다.');
    try {
      books = await savePage(token, baseBooks, books);
      baseBooks = books;
      render();
      notify('GitHub에 저장했습니다. 다른 기기에서 같은 페이지를 열면 최신 목록을 불러옵니다.');
    } catch (error) {
      notify(`저장하지 못했습니다. ${error.message}`, true);
    } finally {
      tokenInput.value = '';
      setBusy(false);
    }
  });
  reloadButton.addEventListener('click', () => reload(true));
  window.addEventListener('beforeunload', event => {
    if (dirty()) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  render();
  reload(false);
}

if (typeof document !== 'undefined') {
  document.querySelectorAll('[data-reading-list]').forEach(mountReadingList);
}
