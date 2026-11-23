/* ETC Monitor dashboard.
 *
 * Data loads when the page opens, when Refresh or "Try again" is pressed, and after
 * an action (cancel, pause/resume, EOD). Nothing reloads on its own. The only timer
 * rewrites the "in 28 min" labels once a minute and never contacts the server.
 *
 * Every piece of text from the API goes into the page with textContent, never as HTML.
 */

import {
  ApiError, getReminders, getReminder, cancelReminder, getBotStatus, setBotPaused, runEodCheck,
} from './api.js';
import {
  parseServerTime, reminderTime, formatClock, formatShortDateTime, relativeLabel, isActive,
  splitUpNext, groupByDay, displayName, displayChannel, matchesSearch,
} from './format.js';

const PAGE_SIZE = 1000;
const UP_NEXT_LIMIT = 10;
const PAST_DUE_LIMIT = 5;
const MINUTE = 60 * 1000;
const SOON_MS = 60 * MINUTE;
const TOAST_MS = 4000;
const ERROR_TOAST_MS = 7000;

const STATUS_LABELS = {
  pending: 'Pending', rescheduled: 'Rescheduled', sent: 'Sent', cancelled: 'Cancelled', failed: 'Failed',
};

const COPY = {
  loadFailed: "Couldn't load ETCs. Check your connection and press Try again.",
  genericError: 'Something went wrong. Please try again.',
  pastDue: ": the bot didn't post these at their time. You can cancel them if they're no longer needed.",
  nothingUpcoming: 'Nothing coming up right now. New reminders appear here when someone gives an ETC in a Slack thread.',
  pause: 'Pause the bot? It stops reading Slack messages, so new ETCs, edits and deletions are ignored until you resume. Reminders already scheduled are still posted.',
  resume: 'Resume the bot? It starts reading Slack messages again.',
  eod: "Posts '👀 Update on this?' in Slack for reminders sent in the last 24 hours that got no reply.",
};

const $ = (id) => document.getElementById(id);

const els = {
  chip: $('bot-chip'),
  chipLabel: $('bot-chip-label'),
  menu: $('bot-menu'),
  toggleItem: $('bot-toggle-item'),
  toggleIconUse: $('bot-toggle-icon').querySelector('use'),
  toggleTitle: $('bot-toggle-title'),
  toggleDesc: $('bot-toggle-desc'),
  eodItem: $('eod-item'),
  updated: $('updated-label'),
  refresh: $('refresh-btn'),
  theme: $('theme-btn'),
  notice: $('notice'),
  noticeText: $('notice-text'),
  noticeRetry: $('notice-retry'),
  toast: $('toast'),
  upNextCount: $('up-next-count'),
  upNextBody: $('up-next-body'),
  upNextMore: $('up-next-more'),
  tabList: $('status-tabs'),
  tabs: Array.from(document.querySelectorAll('#status-tabs [role="tab"]')),
  search: $('search'),
  list: $('etc-list'),
  listFooter: $('list-footer'),
  loadedNote: $('loaded-note'),
  showMore: $('show-more-btn'),
  dialog: $('confirm-dialog'),
  dialogTitle: $('confirm-title'),
  dialogBody: $('confirm-body'),
  dialogOk: $('confirm-ok'),
  dialogCancel: $('confirm-cancel'),
};

const state = {
  loaded: false,
  loadSeq: 0,
  all: [], // newest first, as the server sends them
  total: 0,
  stats: null,
  active: [], // every pending and rescheduled reminder
  botPaused: null,
  tab: 'all',
  query: '',
  showAllUpcoming: false,
  showAllPastDue: false,
};

/* ---------- Small helpers ---------- */

function el(tag, { className, text, attrs } = {}, children = []) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  if (attrs) for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  for (const child of children) if (child != null && child !== false) node.append(child);
  return node;
}

const SVG_NS = 'http://www.w3.org/2000/svg';

function icon(name) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', 'icon');
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

const rowsOf = (response) => (response && Array.isArray(response.reminders) ? response.reminders : []);
const numberOr = (value, fallback) => (Number.isFinite(Number(value)) ? Number(value) : fallback);
const isStatus = (err, code) => err instanceof ApiError && err.status === code;

function statusLabel(status) {
  if (STATUS_LABELS[status]) return STATUS_LABELS[status];
  return status ? String(status).charAt(0).toUpperCase() + String(status).slice(1) : 'Unknown';
}

function statusClass(status) {
  return STATUS_LABELS[status] ? `is-${status}` : 'is-unknown';
}

function errorText(err) {
  return err instanceof ApiError && err.message ? err.message : COPY.genericError;
}

/** "1:00 PM today", "11:00 AM tomorrow", "20 Nov, 5:20 PM" */
function timePhrase(date, now) {
  if (!date) return 'an unknown time';
  const short = formatShortDateTime(date, now);
  const match = /^(Today|Tomorrow|Yesterday) (.+)$/.exec(short);
  return match ? `${match[2]} ${match[1].toLowerCase()}` : short;
}

/* ---------- Toast and notice ---------- */

let toastTimer = null;

function showToast(text, tone = 'info') {
  els.toast.hidden = false;
  els.toast.classList.toggle('is-error', tone === 'error');
  els.toast.textContent = text;
  hideToastLater(tone === 'error' ? ERROR_TOAST_MS : TOAST_MS);
}

function hideToast() {
  els.toast.hidden = true;
}

function hideToastLater(ms) {
  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, ms);
}

function showNotice(text) {
  els.noticeText.textContent = text;
  els.notice.hidden = false;
}

function hideNotice() {
  els.notice.hidden = true;
}

/* ---------- Confirm dialog ---------- */

function confirmAction({ title, body, okLabel, tone = 'primary' }) {
  return new Promise((resolve) => {
    const { dialog } = els;
    const returnFocus = document.activeElement;
    let done = false;

    els.dialogTitle.textContent = title;
    els.dialogBody.textContent = body;
    els.dialogOk.textContent = okLabel;
    els.dialogOk.className = tone === 'danger' ? 'btn btn-danger' : 'btn btn-primary';

    const finish = (result) => {
      if (done) return;
      done = true;
      els.dialogOk.removeEventListener('click', onOk);
      els.dialogCancel.removeEventListener('click', onCancel);
      dialog.removeEventListener('close', onCancel);
      if (dialog.open) dialog.close();
      if (returnFocus && returnFocus.isConnected && typeof returnFocus.focus === 'function') returnFocus.focus();
      resolve(result);
    };
    const onOk = () => finish(true);
    const onCancel = () => finish(false);

    els.dialogOk.addEventListener('click', onOk);
    els.dialogCancel.addEventListener('click', onCancel);
    dialog.addEventListener('close', onCancel); // Escape closes the dialog
    dialog.showModal();
    els.dialogCancel.focus(); // the safe choice has focus
  });
}

/* ---------- Loading ---------- */

function setBusy(busy) {
  els.refresh.setAttribute('aria-busy', String(busy));
  els.refresh.classList.toggle('is-busy', busy);
  els.noticeRetry.disabled = busy;
}

async function loadAll() {
  const seq = ++state.loadSeq;
  setBusy(true);
  try {
    const [bot, all, pending, rescheduled] = await Promise.all([
      getBotStatus(),
      getReminders({ limit: PAGE_SIZE }),
      getReminders({ status: 'pending', limit: PAGE_SIZE }),
      getReminders({ status: 'rescheduled', limit: PAGE_SIZE }),
    ]);
    if (seq !== state.loadSeq) return; // a newer load has started
    state.botPaused = Boolean(bot && bot.paused);
    state.all = rowsOf(all);
    state.total = numberOr(all && all.total, state.all.length);
    state.stats = (all && all.stats) || null;
    state.active = rowsOf(pending).concat(rowsOf(rescheduled));
    state.loaded = true;
    hideNotice();
    els.updated.textContent = `Updated ${formatClock(new Date())}`;
    renderAll();
  } catch (err) {
    if (seq !== state.loadSeq || isStatus(err, 401)) return;
    showNotice(COPY.loadFailed);
    if (!state.loaded) renderNotLoaded();
  } finally {
    if (seq === state.loadSeq) setBusy(false);
  }
}

async function loadMore() {
  els.showMore.disabled = true;
  try {
    const page = await getReminders({ limit: PAGE_SIZE, offset: state.all.length });
    const seen = new Set(state.all.map((r) => r.id));
    const fresh = rowsOf(page).filter((r) => !seen.has(r.id));
    state.all = state.all.concat(fresh);
    state.total = fresh.length ? numberOr(page && page.total, state.total) : state.all.length;
    renderTabs();
    renderList();
  } catch (err) {
    if (!isStatus(err, 401)) showToast(errorText(err), 'error');
  } finally {
    els.showMore.disabled = false;
  }
}

/* ---------- Rendering ---------- */

function renderAll() {
  renderBotChip();
  renderUpNext();
  renderTabs();
  renderList();
}

function renderNotLoaded() {
  renderBotChip();
  els.upNextBody.replaceChildren(el('p', { className: 'loading', text: 'Not loaded yet.' }));
  els.list.replaceChildren(el('p', { className: 'loading', text: 'Not loaded yet.' }));
}

function renderBotChip() {
  const paused = state.botPaused;
  els.chip.classList.toggle('is-running', paused === false);
  els.chip.classList.toggle('is-paused', paused === true);
  els.chipLabel.textContent = paused === null ? 'Bot status unknown' : paused ? 'Bot paused' : 'Bot running';
  els.toggleTitle.textContent = paused ? 'Resume bot' : 'Pause bot';
  els.toggleDesc.textContent = paused
    ? 'Starts reading new ETCs from Slack again.'
    : 'Stops reading new ETCs until you resume.';
  els.toggleIconUse.setAttribute('href', paused ? '#i-play' : '#i-pause');
  els.toggleItem.disabled = paused === null;
}

function emptyState(text) {
  return el('div', { className: 'empty' }, [icon('tray'), el('p', { text })]);
}

function whoBlock(r) {
  return el('div', { className: 'who' }, [
    el('span', { className: 'who-name', text: displayName(r) }),
    el('span', { className: 'who-channel', text: displayChannel(r) }),
  ]);
}

function etcText(r) {
  const text = typeof r.deadline_text === 'string' ? r.deadline_text.trim() : '';
  if (!text) return el('span', { className: 'etc-text is-empty', text: 'No ETC text' });
  return el('span', { className: 'etc-text', text, attrs: { title: text } });
}

function cancelButton(r, when, now) {
  const button = el('button', {
    className: 'btn btn-ghost cancel-btn',
    attrs: { type: 'button', 'aria-label': `Cancel ${displayName(r)}'s reminder for ${timePhrase(when, now)}` },
  }, [icon('x'), el('span', { text: 'Cancel' })]);
  button.dataset.id = String(r.id);
  return button;
}

function upNextRow(r, now, pastDue) {
  const when = reminderTime(r);
  let timeText = 'No time set';
  if (when) timeText = pastDue ? formatShortDateTime(when, now) : formatClock(when);
  const rel = el('span', { className: 'upnext-rel' });
  if (when) {
    rel.dataset.time = String(when.getTime());
    rel.textContent = relativeLabel(when, now);
  }
  return el('div', { className: 'upnext-row' }, [
    el('div', { className: 'upnext-when' }, [el('span', { className: 'upnext-time', text: timeText }), rel]),
    whoBlock(r),
    etcText(r),
    el('div', { className: 'upnext-action' }, [isActive(r) ? cancelButton(r, when, now) : null]),
  ]);
}

function pastDueGroup(pastDue, now) {
  const shown = state.showAllPastDue ? pastDue : pastDue.slice(0, PAST_DUE_LIMIT);
  const group = el('div', { className: 'past-due' }, [
    el('p', { className: 'past-due-head' }, [
      icon('warning'),
      el('span', {}, [el('strong', { text: `Past due (${pastDue.length})` }), COPY.pastDue]),
    ]),
    ...shown.map((r) => upNextRow(r, now, true)),
  ]);
  if (pastDue.length > PAST_DUE_LIMIT) {
    const toggle = el('button', {
      className: 'btn section-more',
      attrs: { type: 'button' },
      text: state.showAllPastDue ? 'Show fewer' : `Show all ${pastDue.length} past due`,
    });
    toggle.addEventListener('click', () => {
      state.showAllPastDue = !state.showAllPastDue;
      renderUpNext();
    });
    group.append(toggle);
  }
  return group;
}

function renderUpNext() {
  const now = new Date();
  const { upcoming, pastDue } = splitUpNext(state.active, now);
  const total = upcoming.length + pastDue.length;
  els.upNextCount.textContent = total ? `${total} pending` : '';

  const nodes = [];
  if (!upcoming.length) {
    nodes.push(emptyState(COPY.nothingUpcoming));
  } else {
    const shown = state.showAllUpcoming ? upcoming : upcoming.slice(0, UP_NEXT_LIMIT);
    for (const group of groupByDay(shown, now)) {
      nodes.push(el('h3', { className: 'day-heading', text: group.heading }));
      for (const r of group.items) nodes.push(upNextRow(r, now, false));
    }
  }
  // The "Show all" button sits right under the upcoming rows, before the past-due group.
  els.upNextMore.hidden = upcoming.length <= UP_NEXT_LIMIT;
  els.upNextMore.textContent = state.showAllUpcoming ? 'Show fewer' : `Show all ${upcoming.length} upcoming`;
  nodes.push(els.upNextMore);
  if (pastDue.length) nodes.push(pastDueGroup(pastDue, now));

  els.upNextBody.replaceChildren(...nodes);
  updateRelativeTimes();
}

function tabCount(status) {
  const stats = state.stats;
  if (status === 'all') return state.total;
  if (status === 'pending') {
    return stats ? (stats.pending || 0) + (stats.rescheduled || 0) : state.active.length;
  }
  return stats ? stats[status] || 0 : state.all.filter((r) => r.status === status).length;
}

function renderTabs() {
  for (const tab of els.tabs) {
    const status = tab.dataset.status;
    const selected = status === state.tab;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    tab.querySelector('[data-count-for]').textContent = state.loaded ? String(tabCount(status)) : '';
  }
}

function rowsForTab() {
  if (state.tab === 'all') return state.all;
  // Pending covers rescheduled too: both are reminders the bot still has to post.
  if (state.tab === 'pending') return state.active.slice().sort((a, b) => (b.id || 0) - (a.id || 0));
  return state.all.filter((r) => r.status === state.tab);
}

function cell(className, label, content) {
  const node = el('div', { className: `etc-cell ${className}`, attrs: { role: 'cell' } });
  if (label) node.dataset.label = label;
  if (content != null) node.append(content);
  return node;
}

function etcRow(r, now) {
  const due = reminderTime(r);
  const created = parseServerTime(r.created_at, 'utc');
  return el('div', { className: 'etc-row', attrs: { role: 'row' } }, [
    cell('etc-person', null, displayName(r)),
    cell('etc-channel', 'Channel', displayChannel(r)),
    cell('etc-etc', 'ETC', etcText(r)),
    cell('etc-due', 'Due', formatShortDateTime(due, now)),
    cell('etc-status', 'Status', el('span', { className: `status ${statusClass(r.status)}`, text: statusLabel(r.status) })),
    cell('etc-created', 'Created', formatShortDateTime(created, now)),
    cell('etc-action', null, isActive(r) ? cancelButton(r, due, now) : null),
  ]);
}

function emptyListText(query) {
  if (query) return `No ETCs match "${query}".`;
  if (state.tab !== 'all') return `No ${statusLabel(state.tab).toLowerCase()} ETCs yet.`;
  return 'No ETCs yet.';
}

function renderList() {
  if (!state.loaded) return;
  const now = new Date();
  const inTab = rowsForTab();
  const query = state.query.trim();
  const rows = query ? inTab.filter((r) => matchesSearch(r, query)) : inTab;

  if (rows.length) els.list.replaceChildren(...rows.map((r) => etcRow(r, now)));
  else els.list.replaceChildren(emptyState(emptyListText(query)));

  const canLoadMore = state.tab !== 'pending' && state.all.length < state.total;
  if (query) {
    els.loadedNote.textContent = canLoadMore
      ? `Found ${rows.length} in the ${state.all.length} most recent ETCs. Press Show more to search older ones.`
      : `Found ${rows.length}.`;
  } else {
    els.loadedNote.textContent = `Showing ${inTab.length} of ${tabCount(state.tab)}`;
  }
  els.showMore.hidden = !canLoadMore;
  els.listFooter.hidden = !query && !inTab.length && !canLoadMore;
}

/* ---------- Relative-time clock (no network) ---------- */

function updateRelativeTimes() {
  const now = new Date();
  for (const node of document.querySelectorAll('[data-time]')) {
    const when = new Date(Number(node.dataset.time));
    node.textContent = relativeLabel(when, now);
    const row = node.closest('.upnext-row');
    if (row && !row.closest('.past-due')) {
      const diff = when.getTime() - now.getTime();
      row.classList.toggle('soon', diff > -5 * MINUTE && diff < SOON_MS);
    }
  }
}

/* ---------- Actions ---------- */

function reportStale(r) {
  showToast(`This ETC is already ${statusLabel(r && r.status).toLowerCase()}. The list has been updated.`);
  loadAll();
}

async function handleCancel(button) {
  const id = button.dataset.id;
  button.disabled = true;
  try {
    let r = await getReminder(id);
    if (!isActive(r)) return reportStale(r);

    const ok = await confirmAction({
      title: 'Cancel reminder',
      body: `Cancel ${displayName(r)}'s reminder for ${timePhrase(reminderTime(r), new Date())}? The bot won't post it, and a short 'Reminder cancelled' note will be posted in the Slack thread.`,
      okLabel: 'Cancel reminder',
      tone: 'danger',
    });
    if (!ok) return undefined;

    // It may have been posted while the dialog was open.
    r = await getReminder(id);
    if (!isActive(r)) return reportStale(r);

    await cancelReminder(id);
    showToast('Reminder cancelled.');
    loadAll();
  } catch (err) {
    if (isStatus(err, 401)) return undefined;
    if (isStatus(err, 404)) showToast('This ETC no longer exists. The list has been updated.');
    else showToast(errorText(err), 'error');
    loadAll();
  } finally {
    if (button.isConnected) button.disabled = false;
  }
  return undefined;
}

async function handleBotToggle() {
  closeMenu(true);
  const pausing = !state.botPaused;
  const ok = await confirmAction(pausing
    ? { title: 'Pause bot', body: COPY.pause, okLabel: 'Pause bot' }
    : { title: 'Resume bot', body: COPY.resume, okLabel: 'Resume bot' });
  if (!ok) return;
  try {
    await setBotPaused(pausing);
    showToast(pausing ? 'Bot paused.' : 'Bot resumed.');
  } catch (err) {
    if (isStatus(err, 401)) return;
    showToast(errorText(err), 'error');
  }
  loadAll();
}

async function handleEod() {
  closeMenu(true);
  const ok = await confirmAction({
    title: 'Run EOD check now',
    body: COPY.eod,
    okLabel: 'Run EOD check',
    tone: 'danger',
  });
  if (!ok) return;
  els.eodItem.disabled = true;
  try {
    const result = await runEodCheck();
    const count = numberOr(result && result.count, 0);
    showToast(`EOD check done. Sent ${count} follow-up(s).`);
  } catch (err) {
    if (isStatus(err, 401)) return;
    showToast(errorText(err), 'error');
  } finally {
    els.eodItem.disabled = false;
  }
  loadAll();
}

/* ---------- Bot menu ---------- */

const enabledMenuItems = () => Array.from(els.menu.querySelectorAll('[role="menuitem"]')).filter((item) => !item.disabled);

function openMenu(focusFirst) {
  els.menu.hidden = false;
  els.chip.setAttribute('aria-expanded', 'true');
  const items = enabledMenuItems();
  if (focusFirst && items.length) items[0].focus();
}

function closeMenu(returnFocus) {
  if (els.menu.hidden) return;
  els.menu.hidden = true;
  els.chip.setAttribute('aria-expanded', 'false');
  if (returnFocus) els.chip.focus();
}

els.chip.addEventListener('click', (event) => {
  if (els.menu.hidden) openMenu(event.detail === 0); // detail 0: opened with the keyboard
  else closeMenu(false);
});

els.chip.addEventListener('keydown', (event) => {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    openMenu(true);
  } else if (event.key === 'Escape') {
    closeMenu(true);
  }
});

els.menu.addEventListener('keydown', (event) => {
  const items = enabledMenuItems();
  if (!items.length) return;
  const index = items.indexOf(document.activeElement);
  let next = null;
  if (event.key === 'ArrowDown') next = items[(index + 1) % items.length];
  else if (event.key === 'ArrowUp') next = items[(index - 1 + items.length) % items.length];
  else if (event.key === 'Home') next = items[0];
  else if (event.key === 'End') next = items[items.length - 1];
  else if (event.key === 'Escape') {
    event.preventDefault();
    closeMenu(true);
  } else if (event.key === 'Tab') {
    closeMenu(false);
  }
  if (next) {
    event.preventDefault();
    next.focus();
  }
});

document.addEventListener('pointerdown', (event) => {
  if (!els.menu.hidden && !event.target.closest('.bot-control')) closeMenu(false);
});

els.toggleItem.addEventListener('click', handleBotToggle);
els.eodItem.addEventListener('click', handleEod);

/* ---------- Tabs, search, buttons ---------- */

function selectTab(status) {
  state.tab = status;
  renderTabs();
  renderList();
}

els.tabList.addEventListener('click', (event) => {
  const tab = event.target.closest('[role="tab"]');
  if (tab) selectTab(tab.dataset.status);
});

els.tabList.addEventListener('keydown', (event) => {
  const index = els.tabs.indexOf(document.activeElement);
  if (index < 0) return;
  let next = null;
  if (event.key === 'ArrowRight') next = els.tabs[(index + 1) % els.tabs.length];
  else if (event.key === 'ArrowLeft') next = els.tabs[(index - 1 + els.tabs.length) % els.tabs.length];
  else if (event.key === 'Home') next = els.tabs[0];
  else if (event.key === 'End') next = els.tabs[els.tabs.length - 1];
  if (next) {
    event.preventDefault();
    selectTab(next.dataset.status);
    next.focus();
  }
});

els.search.addEventListener('input', () => {
  state.query = els.search.value;
  renderList();
});

document.addEventListener('click', (event) => {
  const button = event.target.closest('.cancel-btn');
  if (button && !button.disabled) handleCancel(button);
});

els.upNextMore.addEventListener('click', () => {
  state.showAllUpcoming = !state.showAllUpcoming;
  renderUpNext();
});

els.showMore.addEventListener('click', loadMore);
els.refresh.addEventListener('click', () => loadAll());
els.noticeRetry.addEventListener('click', () => loadAll());

/* ---------- Theme ---------- */

const currentTheme = () => (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');

function renderThemeButton() {
  const label = currentTheme() === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
  els.theme.setAttribute('aria-label', label);
  els.theme.title = label;
}

els.theme.addEventListener('click', () => {
  const next = currentTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem('theme', next);
  } catch (err) {
    /* storage blocked: the choice lasts for this page only */
  }
  renderThemeButton();
});

/* ---------- Start ---------- */

renderThemeButton();
loadAll();
setInterval(updateRelativeTimes, 60_000);
