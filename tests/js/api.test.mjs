// Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ApiError, getReminders } from '../../src/admin/static/js/api.js';

const assigned = [];
globalThis.window = { location: { assign: (url) => assigned.push(url) } };

test('a 200 reply that is not JSON is an error, not empty data', async () => {
  globalThis.fetch = async () => new Response('<html>Proxy page</html>', { status: 200, headers: { 'Content-Type': 'text/html' } });
  await assert.rejects(getReminders(), (err) => err instanceof ApiError && err.status === 200);
});

test('a JSON reply is returned as data', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ total: 0, reminders: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  assert.deepEqual(await getReminders(), { total: 0, reminders: [] });
});

test('a 401 sends the browser to the sign-in page', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });
  await assert.rejects(getReminders(), (err) => err instanceof ApiError && err.status === 401);
  assert.deepEqual(assigned, ['/login']);
});
