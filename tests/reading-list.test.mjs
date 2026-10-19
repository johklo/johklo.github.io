import assert from 'node:assert/strict';
import test from 'node:test';
import {
  decodeContent, encodeContent, loadPage, parsePage, savePage, updatePage, validateBooks
} from '../assets/js/reading-list.mjs';

const books = [{ id: 'first', title: '첫 번째 책', read: false }];
const body = '\n\n{{< reading-list >}}\n\n{{< section-list >}}\n';
const source = JSON.stringify({
  title: 'Book {notes}',
  description: '인용 "기록"과 \\ 경로',
  sidebar: { open: true },
  reading_list: books
}, null, 2) + body;

function reply(status, data) {
  return { ok: status >= 200 && status < 300, status, json: async () => data };
}

function fileResponse(page = source, sha = 'latest-sha') {
  return reply(200, { encoding: 'base64', content: encodeContent(page), sha });
}

test('adding and checking a book preserves all other page data and shortcodes', () => {
  const next = [
    { ...books[0], read: true },
    { id: 'second', title: '한국어와 📚', read: false }
  ];
  const updated = parsePage(updatePage(source, next));
  assert.deepEqual(updated.books, next);
  assert.equal(updated.body, body);
  assert.equal(updated.metadata.title, 'Book {notes}');
  assert.equal(updated.metadata.description, '인용 "기록"과 \\ 경로');
  assert.deepEqual(updated.metadata.sidebar, { open: true });
});

test('page parsing handles CRLF, escaped braces and an empty reading list', () => {
  const windowsSource = source.replaceAll('\n', '\r\n');
  const updated = updatePage(windowsSource, []);
  assert.deepEqual(parsePage(updated).books, []);
  assert.equal(parsePage(updated).body, body.replaceAll('\n', '\r\n'));
  assert(!/(?<!\r)\n/.test(updated));
});

test('invalid pages and book entries fail without silently replacing data', () => {
  for (const value of [null, {}, [{ id: 'a', title: ' ', read: false }],
    [{ id: 'a', title: '책', read: 'false' }],
    [{ id: 'a', title: '책', read: false }, { id: 'a', title: '다른 책', read: true }]
  ]) {
    assert.throws(() => validateBooks(value));
  }
  for (const value of ['---\ntitle: Book\n---', '{"reading_list":[]', '{"reading_list":null}']) {
    assert.throws(() => parsePage(value));
  }
});

test('GitHub base64 preserves Korean, emoji and multiline content', () => {
  const text = source + '인용과 줄바꿈 📚\n';
  const wrapped = encodeContent(text).replace(/.{60}/g, '$&\n');
  assert.equal(decodeContent(wrapped), text);
});

test('saving uses the latest SHA and preserves concurrent non-list edits', async () => {
  const latest = updatePage(source, books).replace('Book {notes}', 'Book updated');
  const calls = [];
  const fetcher = async (url, options) => {
    calls.push({ url, options });
    return options.method === 'PUT'
      ? reply(200, { commit: { sha: 'new-commit' } })
      : fileResponse(latest);
  };
  const next = [{ ...books[0], read: true }];
  assert.deepEqual(await savePage('test-token', books, next, fetcher), next);
  assert.equal(calls.length, 2);
  const payload = JSON.parse(calls[1].options.body);
  assert.equal(payload.sha, 'latest-sha');
  assert.equal(payload.branch, 'master');
  assert.equal(parsePage(decodeContent(payload.content)).metadata.title, 'Book updated');
  assert.equal(calls[1].options.headers.Authorization, 'Bearer test-token');
  assert(!calls[1].options.body.includes('test-token'));
});

test('a reading-list change from another device is not overwritten', async () => {
  let calls = 0;
  const remote = updatePage(source, [{ ...books[0], read: true }]);
  await assert.rejects(
    savePage('test-token', books, [], async () => {
      calls++;
      return fileResponse(remote);
    }),
    /다른 기기/
  );
  assert.equal(calls, 1);
});

test('a SHA conflict is reported without an unsafe retry', async () => {
  let calls = 0;
  await assert.rejects(
    savePage('test-token', books, [], async (_url, options) => {
      calls++;
      return options.method === 'PUT' ? reply(409, {}) : fileResponse();
    }),
    /다른 변경/
  );
  assert.equal(calls, 2);
});

test('a missing token makes no network request', async () => {
  await assert.rejects(
    savePage(' ', books, [], async () => assert.fail('Unexpected network request')),
    /토큰/
  );
});

test('authentication failures and incomplete responses are explicit', async () => {
  await assert.rejects(loadPage('test-token', async () => reply(401, {})), /토큰/);
  await assert.rejects(loadPage('', async () => reply(200, { content: '' })), /올바른 페이지/);
  await assert.rejects(
    savePage('test-token', books, [], async (_url, options) => (
      options.method === 'PUT' ? reply(200, {}) : fileResponse()
    )),
    /저장 결과/
  );
});
