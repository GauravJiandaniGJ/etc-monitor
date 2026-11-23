/* Time and text helpers for the admin dashboard. Pure functions: no DOM, no network.
 *
 * All times are shown in India Standard Time, whatever the viewer's computer is set to.
 * IST is a fixed UTC+05:30 with no daylight saving, so plain offset arithmetic is exact.
 * (Intl output is avoided on purpose: newer browsers put a narrow no-break space before AM/PM.)
 */

export const IST = 'Asia/Kolkata';

const IST_OFFSET_MIN = 330;
const MINUTE = 60 * 1000;
const DAY = 24 * 60 * MINUTE;
// A reminder whose time passed moments ago is still being posted, not "past due".
const PAST_DUE_GRACE_MS = 5 * MINUTE;

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];

const TIME_RE = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?\s*(Z|[+-]\d{2}:?\d{2})?$/i;

/** Parse a server timestamp. Naive values are read as `zone` ('ist' or 'utc'); an explicit offset wins. */
export function parseServerTime(value, zone) {
  if (typeof value !== 'string') return null;
  const m = TIME_RE.exec(value.trim());
  if (!m) return null;
  const [, y, mo, d, h, mi, s = '0', frac = '', tz] = m;
  let offsetMin = zone === 'utc' ? 0 : IST_OFFSET_MIN;
  if (tz) {
    if (tz.toUpperCase() === 'Z') {
      offsetMin = 0;
    } else {
      const digits = tz.slice(1).replace(':', '');
      const sign = tz[0] === '-' ? -1 : 1;
      offsetMin = sign * (Number(digits.slice(0, 2)) * 60 + Number(digits.slice(2, 4)));
    }
  }
  const ms = Number((frac + '000').slice(0, 3));
  const date = new Date(Date.UTC(+y, +mo - 1, +d, +h, +mi, +s, ms) - offsetMin * MINUTE);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** When the bot will post this reminder (falls back to the deadline). */
export function reminderTime(r) {
  return parseServerTime(r && r.reminder_datetime, 'ist') || parseServerTime(r && r.deadline_datetime, 'ist');
}

function istParts(date) {
  const t = new Date(date.getTime() + IST_OFFSET_MIN * MINUTE);
  return { y: t.getUTCFullYear(), m: t.getUTCMonth(), d: t.getUTCDate(), wd: t.getUTCDay(), h: t.getUTCHours(), mi: t.getUTCMinutes(), s: t.getUTCSeconds() };
}

function istDayNumber(date) {
  return Math.floor((date.getTime() + IST_OFFSET_MIN * MINUTE) / DAY);
}

function dayDiff(date, now) {
  return istDayNumber(date) - istDayNumber(now);
}

/** '1:00 PM', or '1:00:05 PM' with { seconds: true } */
export function formatClock(date, { seconds = false } = {}) {
  const { h, mi, s } = istParts(date);
  const secs = seconds ? `:${String(s).padStart(2, '0')}` : '';
  return `${h % 12 || 12}:${String(mi).padStart(2, '0')}${secs} ${h < 12 ? 'AM' : 'PM'}`;
}

/** 'Today, Monday 23 November', 'Wednesday 25 November', 'Monday 4 January 2027' */
export function formatDayHeading(date, now) {
  const p = istParts(date);
  const base = `${DAYS[p.wd]} ${p.d} ${MONTHS[p.m]}`;
  const diff = dayDiff(date, now);
  if (diff === 0) return `Today, ${base}`;
  if (diff === 1) return `Tomorrow, ${base}`;
  if (diff === -1) return `Yesterday, ${base}`;
  return p.y === istParts(now).y ? base : `${base} ${p.y}`;
}

/** 'Today 1:00 PM', '20 Nov, 5:20 PM', '31 Dec 2025, 9:05 AM' */
export function formatShortDateTime(date, now) {
  if (!date) return '—';
  const clock = formatClock(date);
  const diff = dayDiff(date, now);
  if (diff === 0) return `Today ${clock}`;
  if (diff === 1) return `Tomorrow ${clock}`;
  if (diff === -1) return `Yesterday ${clock}`;
  const p = istParts(date);
  const day = `${p.d} ${MONTHS[p.m].slice(0, 3)}`;
  return p.y === istParts(now).y ? `${day}, ${clock}` : `${day} ${p.y}, ${clock}`;
}

/** 'in 28 min', 'in 1 h 28 min', 'in 3 days', 'now', '1 h 2 min ago', '18 days ago' */
export function relativeLabel(date, now) {
  const diffMs = date.getTime() - now.getTime();
  const totalMin = Math.floor(Math.abs(diffMs) / MINUTE);
  if (totalMin < 1) return 'now';
  let text;
  if (totalMin < 60) {
    text = `${totalMin} min`;
  } else if (totalMin < 24 * 60) {
    const h = Math.floor(totalMin / 60);
    const m = totalMin % 60;
    text = m ? `${h} h ${m} min` : `${h} h`;
  } else {
    const days = Math.floor(totalMin / (24 * 60));
    text = days === 1 ? '1 day' : `${days} days`;
  }
  return diffMs > 0 ? `in ${text}` : `${text} ago`;
}

export function isActive(r) {
  return Boolean(r) && (r.status === 'pending' || r.status === 'rescheduled');
}

/** Split active reminders into upcoming (soonest first) and past due (newest first, no-time last). */
export function splitUpNext(reminders, now) {
  const upcoming = [];
  const pastDue = [];
  for (const r of reminders) {
    const t = reminderTime(r);
    if (t && t.getTime() >= now.getTime() - PAST_DUE_GRACE_MS) upcoming.push([t, r]);
    else pastDue.push([t, r]);
  }
  upcoming.sort((a, b) => a[0] - b[0]);
  pastDue.sort((a, b) => (b[0] ? b[0].getTime() : -Infinity) - (a[0] ? a[0].getTime() : -Infinity));
  return { upcoming: upcoming.map(([, r]) => r), pastDue: pastDue.map(([, r]) => r) };
}

/** Group already-sorted reminders under IST day headings. */
export function groupByDay(reminders, now) {
  const groups = [];
  let current = null;
  for (const r of reminders) {
    const t = reminderTime(r);
    const key = t ? istDayNumber(t) : 'none';
    if (!current || current.key !== key) {
      current = { key, heading: t ? formatDayHeading(t, now) : 'No time set', items: [] };
      groups.push(current);
    }
    current.items.push(r);
  }
  return groups.map(({ heading, items }) => ({ heading, items }));
}

export function displayName(r) {
  const name = r && r.user_name;
  if (name && name !== '-') return name;
  const id = r && r.user_id;
  if (id && id !== '-') return id;
  return 'Unknown person';
}

export function displayChannel(r) {
  const raw = (r && (r.channel_name || r.channel_id)) || '';
  if (!raw || raw === '-') return 'Unknown channel';
  return raw.startsWith('#') ? raw : `#${raw}`;
}

/** Case-insensitive match on person, channel and ETC text. A leading '#' is ignored. */
export function matchesSearch(r, query) {
  const q = (query || '').trim().toLowerCase().replace(/^#/, '');
  if (!q) return true;
  const haystack = [displayName(r), r && r.user_id, displayChannel(r), r && r.channel_id, r && r.deadline_text]
    .filter(Boolean).join('\n').toLowerCase();
  return haystack.includes(q);
}
