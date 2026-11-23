// Run: node --test "tests/js/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { createGate } from '../../src/admin/static/js/gate.js';

test('a second action is refused while the first is still running', async () => {
  const gate = createGate();
  let release;
  const calls = [];
  const first = gate.run(() => new Promise((resolve) => { calls.push('first'); release = resolve; }));
  const second = await gate.run(() => { calls.push('second'); });
  assert.equal(second, false);
  assert.equal(gate.busy, true);
  release();
  assert.equal(await first, true);
  assert.deepEqual(calls, ['first']);
  assert.equal(gate.busy, false);
});

test('the gate opens again after an action fails', async () => {
  const gate = createGate();
  await assert.rejects(gate.run(async () => { throw new Error('boom'); }), /boom/);
  assert.equal(gate.busy, false);
  assert.equal(await gate.run(() => {}), true);
});
