// Run: node --test "tests/js/*.test.mjs"   (also under TZ=America/New_York: results must not change)
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  parseServerTime, reminderTime, formatClock, formatDayHeading, formatShortDateTime,
  relativeLabel, isActive, splitUpNext, groupByDay, displayName, displayChannel, matchesSearch,
} from '../../src/admin/static/js/format.js';

const ist = (s) => parseServerTime(s, 'ist');
const now = ist('2026-11-23T12:32:00');

test('parseServerTime reads naive IST and UTC strings', () => {
  assert.equal(ist('2026-11-23T13:00:00').toISOString(), '2026-11-23T07:30:00.000Z');
  assert.equal(ist('2026-11-23 13:00:00').toISOString(), '2026-11-23T07:30:00.000Z');
  assert.equal(parseServerTime('2026-11-20T11:30:47.209034', 'utc').toISOString(), '2026-11-20T11:30:47.209Z');
  assert.equal(parseServerTime('2026-11-20 11:30', 'utc').toISOString(), '2026-11-20T11:30:00.000Z');
});

test('parseServerTime honours an explicit offset and rejects junk', () => {
  assert.equal(parseServerTime('2026-11-23T13:00:00+05:30', 'utc').toISOString(), '2026-11-23T07:30:00.000Z');
  assert.equal(parseServerTime('2026-11-23T07:30:00Z', 'ist').toISOString(), '2026-11-23T07:30:00.000Z');
  assert.equal(parseServerTime(null, 'ist'), null);
  assert.equal(parseServerTime('', 'ist'), null);
  assert.equal(parseServerTime('soon', 'ist'), null);
});

test('reminderTime prefers reminder_datetime and falls back to deadline_datetime', () => {
  assert.equal(reminderTime({ reminder_datetime: '2026-11-23T13:00:00' }).toISOString(), '2026-11-23T07:30:00.000Z');
  assert.equal(reminderTime({ deadline_datetime: '2026-11-23T14:00:00' }).toISOString(), '2026-11-23T08:30:00.000Z');
  assert.equal(reminderTime({}), null);
});

test('formatClock shows IST 12-hour time', () => {
  assert.equal(formatClock(ist('2026-11-23T13:00:00')), '1:00 PM');
  assert.equal(formatClock(ist('2026-11-24T00:05:00')), '12:05 AM');
});

test('relativeLabel counts towards and away from now', () => {
  assert.equal(relativeLabel(ist('2026-11-23T13:00:00'), now), 'in 28 min');
  assert.equal(relativeLabel(ist('2026-11-23T14:00:00'), now), 'in 1 h 28 min');
  assert.equal(relativeLabel(ist('2026-11-23T14:32:00'), now), 'in 2 h');
  assert.equal(relativeLabel(ist('2026-11-26T12:32:00'), now), 'in 3 days');
  assert.equal(relativeLabel(ist('2026-11-24T13:00:00'), now), 'in 1 day');
  assert.equal(relativeLabel(ist('2026-11-23T12:31:30'), now), 'now');
  assert.equal(relativeLabel(ist('2026-11-23T11:30:00'), now), '1 h 2 min ago');
  assert.equal(relativeLabel(ist('2026-11-05T12:00:00'), now), '18 days ago');
});

test('formatDayHeading names days in IST', () => {
  assert.equal(formatDayHeading(ist('2026-11-23T13:00:00'), now), 'Today, Monday 23 November');
  assert.equal(formatDayHeading(ist('2026-11-24T11:00:00'), now), 'Tomorrow, Tuesday 24 November');
  assert.equal(formatDayHeading(ist('2026-11-22T17:00:00'), now), 'Yesterday, Sunday 22 November');
  assert.equal(formatDayHeading(ist('2026-11-25T09:00:00'), now), 'Wednesday 25 November');
  assert.equal(formatDayHeading(ist('2027-01-04T09:00:00'), now), 'Monday 4 January 2027');
});

test('formatDayHeading uses the IST calendar day, not the viewer\'s', () => {
  const lateNight = ist('2026-11-23T23:50:00');
  assert.equal(formatDayHeading(ist('2026-11-24T00:10:00'), lateNight), 'Tomorrow, Tuesday 24 November');
});

test('formatShortDateTime is short and relative to today', () => {
  assert.equal(formatShortDateTime(ist('2026-11-23T13:00:00'), now), 'Today 1:00 PM');
  assert.equal(formatShortDateTime(ist('2026-11-24T11:00:00'), now), 'Tomorrow 11:00 AM');
  assert.equal(formatShortDateTime(ist('2026-11-22T17:00:00'), now), 'Yesterday 5:00 PM');
  assert.equal(formatShortDateTime(ist('2026-11-20T17:20:00'), now), '20 Nov, 5:20 PM');
  assert.equal(formatShortDateTime(ist('2025-12-31T09:05:00'), now), '31 Dec 2025, 9:05 AM');
  assert.equal(formatShortDateTime(null, now), '—');
});

test('isActive covers pending and rescheduled only', () => {
  assert.equal(isActive({ status: 'pending' }), true);
  assert.equal(isActive({ status: 'rescheduled' }), true);
  assert.equal(isActive({ status: 'sent' }), false);
  assert.equal(isActive({}), false);
});

test('splitUpNext orders upcoming soonest first and past due newest first', () => {
  const at = (id, s) => ({ id, reminder_datetime: s });
  const { upcoming, pastDue } = splitUpNext([
    at('+4h', '2026-11-23T16:32:00'),
    at('-18d', '2026-11-05T12:32:00'),
    at('+28m', '2026-11-23T13:00:00'),
    at('-2d', '2026-11-21T12:32:00'),
    at('none', null),
  ], now);
  assert.deepEqual(upcoming.map((r) => r.id), ['+28m', '+4h']);
  assert.deepEqual(pastDue.map((r) => r.id), ['-2d', '-18d', 'none']);
});

test('groupByDay groups under IST day headings in order', () => {
  const at = (id, s) => ({ id, reminder_datetime: s });
  const groups = groupByDay([at('a', '2026-11-23T13:00:00'), at('b', '2026-11-23T17:00:00'), at('c', '2026-11-24T11:00:00')], now);
  assert.deepEqual(groups.map((g) => [g.heading, g.items.map((r) => r.id)]), [
    ['Today, Monday 23 November', ['a', 'b']],
    ['Tomorrow, Tuesday 24 November', ['c']],
  ]);
});

test('displayName and displayChannel fall back sensibly', () => {
  assert.equal(displayName({ user_name: 'Priya Raman', user_id: 'U1' }), 'Priya Raman');
  assert.equal(displayName({ user_name: 'U1', user_id: 'U1' }), 'U1');
  assert.equal(displayName({ user_name: null, user_id: 'U9' }), 'U9');
  assert.equal(displayName({}), 'Unknown person');
  assert.equal(displayChannel({ channel_name: 'booking101' }), '#booking101');
  assert.equal(displayChannel({ channel_name: '#x' }), '#x');
  assert.equal(displayChannel({ channel_id: 'C1' }), '#C1');
  assert.equal(displayChannel({}), 'Unknown channel');
});

test('matchesSearch looks at person, channel and ETC text, ignoring case', () => {
  const r = { user_name: 'Priya Raman', user_id: 'U1', channel_name: 'booking101', channel_id: 'C1', deadline_text: 'by 1pm' };
  assert.equal(matchesSearch(r, 'priya'), true);
  assert.equal(matchesSearch(r, '#BOOKING'), true);
  assert.equal(matchesSearch(r, 'by 1pm'), true);
  assert.equal(matchesSearch(r, '  '), true);
  assert.equal(matchesSearch(r, ''), true);
  assert.equal(matchesSearch(r, 'zzz'), false);
  assert.equal(matchesSearch({}, 'x'), false);
});
