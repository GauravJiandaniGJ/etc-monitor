# Admin Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the admin dashboard and login page in the approved "warm and classic" style, with a dark version, upcoming ETCs first and no auto-reload. Also fix the Postgres-breaking EOD follow-up query.

**Architecture:**
- Same Flask app and endpoints, server-rendered Jinja templates, plain CSS, and native ES modules with no build step.
- Pure time and text logic lives in `format.js`, tested with Node's built-in test runner.
- `api.js` wraps `fetch`; `dashboard.js` owns state and builds the DOM with `textContent` only.
- One SQL expression in the repository changes; it is tested on SQLite and on a throwaway local Postgres.

**Tech Stack:** Flask/Jinja, vanilla JS (ES modules), CSS custom properties, Phosphor Icons 2.1.1 (MIT, inline SVG sprite), pytest, `node --test` (Node 24, no packages), local PostgreSQL 14 for one check, Playwright MCP for browser checks.

**Spec:** `docs/superpowers/specs/2026-11-23-admin-dashboard-redesign-design.md`

## Global Constraints

- **Worktree:** a separate git worktree (`../etc-monitor-admin-login`), branch `feat/admin-login`. Python: `../etc-monitor/env/bin/python`.
- **Allowed changes:** `src/admin/templates/*`, `src/admin/static/*`, `tests/*`, `docs/superpowers/*`, and only `get_pending_followups` in `src/database/repositories/reminder_repository.py`. Nothing else changes, in particular `src/bot`, `src/services`, `src/config`, migrations and `app.py`.
- **No polling:** no timer may fetch data. The only interval is the 60 s relative-label clock, which never touches the network.
- **No raw HTML:** no `innerHTML`, `outerHTML` or `insertAdjacentHTML` anywhere in `src/admin/static/js/`.
- **No external requests:** no Google Fonts, no CDN.
- **Fonts:** serif `"Iowan Old Style", Charter, Georgia, serif` for the brand, section headings and the italic day labels. System stack `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` for everything else. Times use `font-variant-numeric: tabular-nums`.
- **Light tokens:** bg `#faf8f5`, surface `#fffdf9`, surface-2 `#f3efe8`, border `#e7e2da`, border-strong `#d6cfc4`, text `#1c1917`, text-2 `#44403c`, muted `#78716c`, faint `#a8a29e`, accent `#c2410c`, success `#15803d`, danger `#b42318`.
- **Dark tokens:** bg `#171412`, surface `#1c1916`, surface-2 `#23201c`, border `#2c2723`, border-strong `#38322c`, text `#ece5da`, text-2 `#d6cec2`, muted `#a39a8e`, faint `#6f675e`, accent `#f08a4b`, success `#6cc28a`, danger `#f19a8a`.
- **Theme:**
  - `localStorage` key `theme` with values `light` or `dark`, as today. When it's absent, follow `prefers-color-scheme`.
  - Applied as `data-theme` on `<html>` before first paint, on both pages.
  - Every `localStorage` access is wrapped in try/catch.
- **Times:** shown in `Asia/Kolkata` whatever the viewer's zone is.
  - `reminder_datetime` and `deadline_datetime` are naive IST.
  - `created_at` is naive UTC.
  - `sent_at` and `updated_at` are never displayed.
- **Copy (fixed by the spec):**
  - Up next helper: "Reminders the bot will post in Slack, soonest first."
  - Past-due line: "Past due (N): the bot didn't post these at their time. You can cancel them if they're no longer needed."
  - EOD menu text: "Posts '👀 Update on this?' in Slack for reminders sent in the last 24 hours that got no reply."
  - EOD result: "Sent N follow-up(s)."
  - Cancel confirm: "Cancel {person}'s reminder for {time}? The bot won't post it, and a short 'Reminder cancelled' note will be posted in the Slack thread."
  - Pause confirm (from bot code: pause only skips incoming Slack message events): "Pause the bot? It stops reading Slack messages, so new ETCs, edits and deletions are ignored until you resume. Reminders already scheduled are still posted."
- **Login contract:** the form keeps exactly 2 `<input>`s (`username`, `password`) posting to `url_for('login')`, and the dashboard keeps `href="/logout"`.
- **Commits:** each ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Nothing is pushed until Task 7.

## Review Focus

1. **The viewer's computer isn't in IST.** Times and Today/Tomorrow headings must still be IST. Pinned in Task 2 by running the Node tests under `TZ=America/New_York`.
2. **Missing or odd data.** Cases: name null or equal to the ID, channel null, ETC text null or 300+ characters, `reminder_datetime` null. The row still renders with fallbacks, and long text wraps without widening the page. Pinned in Task 2 (fallback tests) and Task 6 (seeded rows).
3. **HTML or script in Slack names or ETC text.** It must show as literal text. Pinned in Task 5 (static test against `innerHTML`) and Task 6 (seeded `<img onerror>` row).
4. **A stale page cancelling a reminder that was already sent or cancelled.** No cancel request may be sent; explain it and refresh instead. Pinned in Task 6 (change the status in the DB, then click Cancel).
5. **The server is unreachable or the session expired during Refresh or an action.** Data already shown stays, an error with "Try again" appears, and a 401 goes to `/login`. Pinned in Task 6 (stop the server, then Refresh).

---

### Task 0: Local test harness and "before" screenshots

These are scratchpad-only files and are not committed. `$SP` is the session's scratch directory.

**Files:**
- Create: `$SP/ui-harness/seed_local.py`, `$SP/ui-harness/run_local_admin.py`

**Interfaces:**
- **Produces:** a local admin on `http://localhost:5051` backed by `$SP/ui-harness/ui-test.db`, with a local-only test login from the worktree's git-ignored `.env`. Slack calls are stubbed, and every `chat_postMessage` is appended to `$SP/ui-harness/slack-calls.log`.

- [ ] **Step 1:** Write `seed_local.py`.
  - Delete and recreate `ui-test.db`, run `MigrationManager(db).run_pending()`, then insert through `ReminderRepository.create` / `update`.
  - Times are relative to `now_ist()`, stored naive IST. Rows:
    - **pending:** +28 min, +1 h 28 min, +4 h 28 min (with 320-character ETC text), tomorrow 11:00, +3 days;
    - **pending past due:** −2 days, −18 days, 2026-01-20 10:00;
    - **sent:** 30 rows spread over the last 30 days;
    - **cancelled:** 5;
    - **failed:** 1;
    - **pending:** one with `deadline_text='<img src=x onerror=alert(1)> by 5pm'`;
    - **pending:** one with `deadline_text=None` and `reminder_datetime=None`.
  - Then set varied `created_at` values in UTC with direct SQL.
  - Flags: `--many` adds 1,050 extra `sent` rows; `--empty` creates the schema only.
- [ ] **Step 2:** Write `run_local_admin.py`.
  - Set `DATABASE_PATH` to `ui-test.db`, then `create_app()`.
  - Pre-fill `reminder_routes._user_cache` and `_channel_cache` with made-up names. Include one name `'<b>Mallory</b>'`, and leave one user uncached so it falls back to the user ID.
  - Replace `reminder_routes._slack_client` and `_notification_service.client` with a stub. Its `chat_postMessage(**kw)` logs `kw` and returns `{'ok': True}`; its `users_info` / `conversations_info` return `{'ok': False}`.
  - Run on 5051.
- [ ] **Step 3:** Seed, start the harness in the background, log in with Playwright, and take full-page screenshots of the **current** dashboard at 1280×900 and 390×844, saved as `before-desktop.png` and `before-mobile.png`. Expected: the old UI renders with the seeded rows.

### Task 1: EOD follow-up query works on Postgres

**Files:**
- Modify: `src/database/repositories/reminder_repository.py:201-227` (`get_pending_followups` only)
- Test: `tests/unit/test_eod_followups.py`

**Interfaces:**
- **Consumes:** `ReminderRepository.create(Reminder) -> int`, `.update(id, dict) -> bool`, `MigrationManager(db).run_pending()`, the `mock_settings` fixture.
- **Produces:** `get_pending_followups() -> List[Reminder]`, with the same signature and behaviour, now portable.

- [ ] **Step 1: Write the failing tests.**
  - Fixtures:
    - `sqlite_repo` uses `mock_settings` with `database_path` set to a `tmp_path` file, plus migrations.
    - `postgres_repo` reads env `ETC_TEST_PG_HOST` (socket dir), `ETC_TEST_PG_PORT`, `ETC_TEST_PG_DB` and `ETC_TEST_PG_USER`. It **skips** when they are unset, otherwise sets `database_type='postgresql'` and the host/port/name/user fields, then runs migrations.
  - `repo` is parametrized over both.
  - Helper `_sent(repo, hours_ago, **extra) -> int` creates a reminder and updates it with `status='sent'` and `sent_at` = `reminder_sent_at` = `datetime.now() - timedelta(hours=hours_ago)`.

```python
def test_includes_reminder_sent_recently_without_reply(repo):
    rid = _sent(repo, 1)
    assert [r.id for r in repo.get_pending_followups()] == [rid]

def test_excludes_reminder_sent_more_than_24h_ago(repo):
    _sent(repo, 30)
    assert repo.get_pending_followups() == []

def test_excludes_when_followup_already_sent(repo):
    _sent(repo, 1, followup_sent_at=datetime.now())
    assert repo.get_pending_followups() == []

def test_excludes_when_user_replied_after_reminder(repo):
    _sent(repo, 2, last_user_update_at=datetime.now() - timedelta(hours=1))
    assert repo.get_pending_followups() == []

def test_excludes_pending_reminders(repo):
    repo.create(make_reminder(status=ReminderStatus.PENDING))
    assert repo.get_pending_followups() == []
```

- [ ] **Step 2: Run the tests on SQLite.**
  - Command: `../etc-monitor/env/bin/python -m pytest tests/unit/test_eod_followups.py -o addopts="" -q`
  - Expected: the SQLite cases pass, because `datetime()` exists there, and the Postgres cases are skipped.
- [ ] **Step 3: Start a throwaway Postgres and confirm the failure.**
  - Commands:
    - `initdb -D $SP/pg -U etc --auth=trust`
    - `pg_ctl -D $SP/pg -o "-p 54329 -k $SP/pgsock -c listen_addresses=''" -l $SP/pg.log start`
    - `createdb -h $SP/pgsock -p 54329 -U etc etc_test`
  - Run the tests with the `ETC_TEST_PG_*` env set.
  - Expected: the Postgres cases **FAIL** with `function datetime(unknown, unknown) does not exist`.
- [ ] **Step 4: Implement the fix.**
  - In `get_pending_followups`, replace `datetime('now', '-24 hours')` with `?`.
  - Pass `(self._datetime_to_str(datetime.now() - timedelta(hours=24)),)` to `fetch_all`.
  - Add `timedelta` to the existing `datetime` import if it's missing.
  - Update the docstring to say why the cutoff is computed in Python.
- [ ] **Step 5: Run the tests on both databases.** Expected: 10 passed (5 × SQLite, 5 × Postgres). Stop the cluster with `pg_ctl -D $SP/pg stop`.
- [ ] **Step 6: Commit.** Message: `Fix EOD follow-up query on Postgres`.

### Task 2: Time and text helpers

**Files:**
- Create: `src/admin/static/js/format.js`
- Test: `tests/js/format.test.mjs`

**Interfaces:**
- **Produces**, all named exports and all pure, with `now` passed in:
  - `IST = 'Asia/Kolkata'`
  - `parseServerTime(value: string|null, zone: 'ist'|'utc') -> Date|null`. It accepts `YYYY-MM-DD[T ]HH:MM[:SS[.fraction]]`, with an optional `Z` or `±HH:MM` that overrides `zone`. Anything else gives `null`.
  - `reminderTime(r) -> Date|null`, from `reminder_datetime`, falling back to `deadline_datetime`, read as IST.
  - `formatClock(date) -> string`, e.g. `'1:00 PM'`.
  - `formatDayHeading(date, now) -> string`.
  - `formatShortDateTime(date, now) -> string`.
  - `relativeLabel(date, now) -> string`.
  - `isActive(r) -> boolean` (`pending` | `rescheduled`).
  - `splitUpNext(activeReminders, now) -> {upcoming: r[], pastDue: r[]}`. `upcoming` is ascending by time. `pastDue` is newest first and includes null-time rows last.
  - `groupByDay(reminders, now) -> Array<{heading: string, items: r[]}>`.
  - `displayName(r) -> string`, `displayChannel(r) -> string`.
  - `matchesSearch(r, query) -> boolean`.

- [ ] **Step 1: Write the failing tests** with `node:test` and `node:assert/strict`, using `const now = parseServerTime('2026-11-23T12:32:00', 'ist')`.
  - `parseServerTime('2026-11-23T13:00:00','ist').toISOString() === '2026-11-23T07:30:00.000Z'`
  - `parseServerTime('2026-11-23 13:00:00','ist')` gives the same instant.
  - `parseServerTime('2026-11-20T11:30:47.209034','utc').toISOString() === '2026-11-20T11:30:47.209Z'`
  - `parseServerTime('2026-11-23T13:00:00+05:30','utc').toISOString() === '2026-11-23T07:30:00.000Z'`
  - `parseServerTime(null,'ist') === null` and `parseServerTime('soon','ist') === null`
  - `formatClock(ist('2026-11-23T13:00:00')) === '1:00 PM'`
  - `relativeLabel` results: 13:00 gives `'in 28 min'`; 14:00 gives `'in 1 h 28 min'`; 14:32 gives `'in 2 h'`; `2026-11-26T12:32` gives `'in 3 days'`; 12:31:30 gives `'now'`; 11:30 gives `'1 h 2 min ago'`; `2026-11-05T12:00` gives `'18 days ago'`.
  - `formatDayHeading` results: 13:00 gives `'Today, Monday 23 November'`; `2026-11-24T11:00` gives `'Tomorrow, Tuesday 24 November'`; `2026-11-22T17:00` gives `'Yesterday, Sunday 22 November'`; `2026-11-25T09:00` gives `'Wednesday 25 November'`; `2027-01-04T09:00` gives `'Monday 4 January 2027'`.
  - `formatShortDateTime` results: today 13:00 gives `'Today 1:00 PM'`; tomorrow 11:00 gives `'Tomorrow 11:00 AM'`; `2026-11-20T17:20` gives `'20 Nov, 5:20 PM'`; `2025-12-31T09:05` gives `'31 Dec 2025, 9:05 AM'`.
  - **IST day boundary:** with `now` at `2026-11-23T23:50` IST, an item at `2026-11-24T00:10` IST is headed `'Tomorrow, Tuesday 24 November'`.
  - **`splitUpNext`:** given rows at +4 h, past −18 d, +28 min, past −2 d and null time, `upcoming` comes out as [+28 min, +4 h] and `pastDue` as [−2 d, −18 d, null].
  - **`displayName`:**
    - `{user_name:'Priya Raman',user_id:'U1'}` gives `'Priya Raman'`;
    - `{user_name:'U1',user_id:'U1'}` gives `'U1'`;
    - `{}` gives `'Unknown person'`.
  - **`displayChannel`:**
    - `{channel_name:'booking101'}` gives `'#booking101'`;
    - `{channel_name:'#x'}` gives `'#x'`;
    - `{channel_id:'C1'}` gives `'#C1'`;
    - `{}` gives `'Unknown channel'`.
  - **`matchesSearch`:** true for `'priya'`, `'#BOOKING'` and `'by 1pm'` against the matching fields, and for `''`; false for `'zzz'`.
- [ ] **Step 2: Run and confirm failure.** `node --test tests/js/` fails because the module is missing.
- [ ] **Step 3: Implement `format.js`.**
  - Use `Intl.DateTimeFormat('en-GB'|'en-US', {timeZone: IST, ...})`, with en-US for the clock (`h:mm AM`) and en-GB for day/month order.
  - Compare calendar days with `istDateKey(date)` (`YYYY-MM-DD` in IST).
  - Relative labels:
    - under 60 s: `now`;
    - under 60 min: `N min`;
    - under 24 h: `H h` plus ` M min` when M > 0;
    - otherwise: `D day(s)`;
    - all prefixed `in ` or suffixed ` ago`.
- [ ] **Step 4: Run under both zones.**
  - Commands: `TZ=Asia/Kolkata node --test tests/js/` and `TZ=America/New_York node --test tests/js/`
  - Expected: all pass in both.
- [ ] **Step 5: Commit.** Message: `Add IST time and text helpers for the dashboard`.

### Task 3: Shared look, icons, and the login page

**Files:**
- Create:
  - `src/admin/templates/_icons.html`: a hidden `<svg>` sprite of `<symbol id="i-NAME" viewBox="0 0 256 256">` for `arrow-clockwise`, `magnifying-glass`, `x`, `sign-out`, `pause`, `play`, `lightning`, `sun`, `moon`, `caret-down`, `warning`, `tray` and `check-circle`, copied from `$SP/phosphor/*.svg` (Phosphor 2.1.1 regular). It is preceded by an HTML comment holding the full Phosphor MIT license from `$SP/phosphor/LICENSE`.
  - `src/admin/templates/_theme_boot.html`: an inline `<script>` that sets `document.documentElement.dataset.theme` from `localStorage.theme`, or from `prefers-color-scheme` when absent.
  - `src/admin/static/css/base.css`: tokens, reset, typography, `.btn` (`.btn`, `.btn-primary`, `.btn-ghost`), `.icon` (1em), `.field`, `:focus-visible` (2px accent outline, 2px offset), `.visually-hidden`.
  - `src/admin/static/css/login.css`
- Modify: `src/admin/templates/login.html` (full restyle, same form contract)
- Test: `tests/integration/test_admin_ui.py`

**Interfaces:**
- **Produces:**
  - Jinja includes `{% include '_theme_boot.html' %}` (in `<head>`, before the CSS) and `{% include '_icons.html' %}` (first in `<body>`).
  - Icon markup: `<svg class="icon" aria-hidden="true"><use href="#i-NAME"></use></svg>`.
  - Token names `--bg --surface --surface-2 --border --border-strong --text --text-2 --muted --faint --accent --success --danger`.

- [ ] **Step 1: Write the failing tests** in `tests/integration/test_admin_ui.py`, reusing the `_build_app` and `_login` patterns from `test_admin_auth.py`.
  - `test_login_page_uses_local_styles_only`: the `/login` HTML contains `css/base.css` and `css/login.css`, and does not contain `fonts.googleapis`.
  - `test_login_page_sets_theme_before_paint`: the `<head>` part of the HTML contains `localStorage` and `prefers-color-scheme`.
  - `test_icon_sprite_has_license_and_symbols`: the HTML contains `Phosphor Icons`, `MIT License`, `id="i-warning"` and `id="i-sign-out"`.
  - `test_login_error_is_announced`: a failed login's HTML contains `role="alert"` and `Invalid username or password`.
- [ ] **Step 2: Run them.** Command: `../etc-monitor/env/bin/python -m pytest tests/integration/test_admin_ui.py -o addopts="" -q`. Expected: the first three FAIL.
- [ ] **Step 3: Implement the files listed above.**
  - The login card follows the approved mockup:
    - serif "ETC Monitor" title, subtitle "Sign in to manage reminders.";
    - Username and Password labels, a dark full-width "Sign in" button;
    - footer "Session lasts 7 days on this device.";
    - error box with `i-warning` and `role="alert"`;
    - dark theme through the tokens;
    - card max-width 360 px, 16 px side gutter on phones.
- [ ] **Step 4: Run** `test_admin_ui.py` and `test_admin_auth.py`. Expected: all pass, including `test_login_page_has_only_username_and_password`.
- [ ] **Step 5: Commit.** Message: `Restyle login page and add shared styles and icons`.

### Task 4: Dashboard page structure and styles

**Files:**
- Modify: `src/admin/templates/dashboard.html` (full rewrite)
- Modify: `src/admin/static/css/dashboard.css` (full rewrite)
- Test: `tests/integration/test_admin_ui.py`

**Interfaces:**
- **Produces:** element IDs for `dashboard.js`.
  - **Header:**
    - `#bot-chip` (button, `aria-haspopup="menu"`, `aria-expanded`, `aria-controls="bot-menu"`), with children `#bot-chip-dot` and `#bot-chip-label`;
    - `#bot-menu` (`role="menu"`, `hidden`), with `#bot-toggle-item` (children `#bot-toggle-icon`, `#bot-toggle-title`, `#bot-toggle-desc`) and `#eod-item`;
    - `#updated-label`;
    - `#refresh-btn`;
    - `#theme-btn`, with `aria-label` and `title`;
    - `<a id="logout-link" href="{{ url_for('logout') }}">`, with the `sign-out` icon and the text "Sign out".
  - **Messages:** `#notice` (`role="status"`, `aria-live="polite"`, hidden; holds an error message and a `#notice-retry` "Try again" button) and `#toast` (`aria-live="polite"`).
  - **Up next:** `section#up-next` with h2 "Up next", `#up-next-count`, the helper `<p>`, `#up-next-body` and `#up-next-more`.
  - **All ETCs:**
    - `section#all-etcs` with h2 "All ETCs" and the helper "Everything the bot has picked up. Use the tabs or search to find one.";
    - `#status-tabs` (`role="tablist"`) holding five `button[role=tab][data-status]` for `all`, `pending`, `sent`, `cancelled` and `failed`, each with `span[data-count-for]`;
    - `label[for=search]` "Search", plus `input#search` (`type="search"`, placeholder "Search by person, channel or ETC text");
    - `#etc-list`, plus `#list-footer` containing `#loaded-note` and `#show-more-btn`.
  - **Confirm dialog:** `dialog#confirm-dialog` with `#confirm-title`, `#confirm-body`, `#confirm-ok` and `#confirm-cancel`.
  - **Script:** `<script type="module" src="…/js/dashboard.js">`.
  - **CSS classes:** `.upnext-row`, `.day-heading`, `.etc-row`, `.status` with modifiers `.is-pending`, `.is-sent`, `.is-cancelled`, `.is-failed` and `.is-rescheduled`, `.soon` (time under 60 min, accent colour), `.past-due`, `.empty`.

- [ ] **Step 1: Write the failing test** `test_dashboard_has_new_layout`. Logged in, `GET /` contains each of:
  - `id="up-next"`, `id="all-etcs"`, `id="refresh-btn"`, `id="bot-menu"`, `id="confirm-dialog"`;
  - `href="/logout"`, `type="module"`, `css/base.css`.

  It does not contain any of `trigger-eod-btn`, `bot-toggle-btn` or `fonts.googleapis`.
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement the template and CSS** to match the approved mockups.
  - **Header:** a single row, with the serif brand on the left and the controls on the right.
  - **Up next rows:** a grid with columns `92px 1.1fr 2fr auto` (time+relative, person+channel, ETC text, Cancel). The ETC text is clamped to 2 lines, with the full text in `title`.
  - **All ETCs rows:** columns Person, Channel, ETC, Due, Status, Created, action.
  - **Tabs:** underline style with the accent underline on the active tab.
  - **Phone (`@media (max-width: 720px)`):** the header wraps, `#updated-label` is hidden, and rows become stacked blocks with labels. Nothing may overflow horizontally at 360 px.
  - **Cancel:** an always-visible `.btn-ghost` with the `x` icon and the text "Cancel".
- [ ] **Step 4: Run** `test_admin_ui.py` and `test_admin_auth.py`. Expected: all pass.
- [ ] **Step 5: Commit.** Message: `Rebuild dashboard layout and styles`.

### Task 5: Dashboard behaviour

**Files:**
- Create: `src/admin/static/js/api.js`
- Modify: `src/admin/static/js/dashboard.js` (full rewrite as an ES module)
- Test: `tests/integration/test_admin_ui.py`

**Interfaces:**
- **Consumes:** the `format.js` exports (Task 2) and the element IDs and classes (Task 4).
- **Produces (`api.js`):**
  - `class ApiError extends Error {status}`;
  - `getReminders({status, limit, offset}) -> {total, reminders, stats}`;
  - `getReminder(id) -> reminder`;
  - `cancelReminder(id) -> reminder`;
  - `getBotStatus() -> {paused}`;
  - `setBotPaused(paused: boolean) -> {success, status}`;
  - `runEodCheck() -> {success, count, message}`.
  - On a 401, every call sends the browser to `/login` (`window.location.assign('/login')`) and throws `ApiError`.

- [ ] **Step 1: Write the failing static tests.**
  - `test_dashboard_js_never_polls`: across `src/admin/static/js/*.js`, `setInterval(` appears exactly once, on a line containing `updateRelativeTimes`. Every line with `setTimeout(` contains `hideToast`. `location.reload` never appears.
  - `test_js_never_injects_html`: no JS file contains `innerHTML`, `outerHTML` or `insertAdjacentHTML`.
  - `test_js_served_as_javascript`: `/static/js/dashboard.js`, `/static/js/format.js` and `/static/js/api.js` return 200 with a `javascript` mimetype.
- [ ] **Step 2: Run them.** Expected: the first two FAIL against the old `dashboard.js`.
- [ ] **Step 3: Implement `api.js` and `dashboard.js`.**
  - **Loading:** `loadAll()` runs on start, on `#refresh-btn`, on `#notice-retry` and after every action.
    - It runs `Promise.all` over `getBotStatus()`, `getReminders({limit:1000})`, `getReminders({status:'pending',limit:1000})` and `getReminders({status:'rescheduled',limit:1000})`.
    - Existing content stays on screen while loading. `#refresh-btn` gets `aria-busy` and a spinning icon.
    - On success it sets `#updated-label` to "Updated 12:30" (IST clock).
    - On failure it shows `#notice` with "Couldn't load ETCs. Check your connection and press Try again." and keeps the old data.
  - **Up next:** `splitUpNext` and `groupByDay` produce the day headings.
    - Show the first 10 upcoming rows, then `#up-next-more` "Show all N pending".
    - The past-due group follows, with its fixed line and the `warning` icon.
    - When nothing is upcoming, show the empty state: `tray` icon and "Nothing coming up right now."
  - **All ETCs:**
    - Tab counts come from `stats` and `total`.
    - Tabs filter the loaded rows by status, and `matchesSearch` filters as you type.
    - `#loaded-note` reads "Showing N of TOTAL". `#show-more-btn` is shown only when loaded < total, and it fetches `offset=loaded`.
    - The empty result reads "No ETCs match "{query}".", or "No {status} ETCs yet." on a status tab, or "No ETCs yet." on All.
    - Active rows get Cancel.
  - **Cancel:**
    - First `getReminder(id)`. If the reminder isn't active, show the toast "This ETC is already {status}. The list has been updated." and run `loadAll()`.
    - Otherwise show the confirm dialog with the fixed copy, then `cancelReminder` and the toast "Reminder cancelled.", then `loadAll()`.
  - **Bot menu:**
    - The chip toggles the menu. Escape and clicking outside close it. Arrow keys move between items. Focus returns to the chip.
    - The toggle item shows "Pause bot" or "Resume bot" with its description. The confirm dialog uses the fixed pause copy, or "Resume the bot? It starts reading Slack messages again."
    - The EOD item opens a confirm, then `runEodCheck()`, then the toast "EOD check done. Sent N follow-up(s).", then `loadAll()`.
    - The chip label reads "Bot running" or "Bot paused". The dot is green or accent, and the text label is always present.
  - **Clock:** `updateRelativeTimes()` rewrites every `[data-time]` element's relative text and `.soon` class. It is started once with `setInterval(updateRelativeTimes, 60_000)` and makes no network calls.
  - **Theme:** `#theme-btn` flips `data-theme`, saves it to `localStorage.theme` (try/catch), and swaps the `sun`/`moon` icon and the label "Switch to dark mode" / "Switch to light mode".
  - **Toasts and errors:** `showToast(text, tone)` with `hideToastLater()` (`setTimeout`, 4 s). Action failures show a toast with the server's `error` text, or "Something went wrong. Please try again."
  - **DOM building:** only `document.createElement`, `textContent`, `setAttribute`, `replaceChildren`, and an `icon(name)` helper that builds the `<svg><use>`.
- [ ] **Step 4: Run all tests.**
  - Commands: `../etc-monitor/env/bin/python -m pytest tests/integration/test_admin_ui.py tests/integration/test_admin_auth.py tests/unit/test_eod_followups.py -o addopts="" -q` and `node --test tests/js/`
  - Expected: all pass.
- [ ] **Step 5: Commit.** Message: `Rebuild dashboard behaviour without auto-refresh`.

### Task 6: Browser verification and "after" screenshots

Uses the Task 0 harness and Playwright, local only. Reseed before each run.

- [ ] **Step 1: Desktop light, 1280×900.**
  - Log in. Up next shows Today (3 rows, the first in accent with "in 28 min"), Tomorrow, then later days.
  - The past-due group is last and lists 3 rows plus the null-time row.
  - The `<img onerror>` text shows literally and no alert fires. `<b>Mallory</b>` shows literally.
  - The 320-character ETC text is clamped, with the full text in its tooltip.
  - Screenshot `after-desktop-light.png`.
- [ ] **Step 2: No polling.**
  - Record network requests, wait 75 s, and count `/api/` requests after the initial load. Expected: **0**.
  - The relative labels have changed by 1 minute.
- [ ] **Step 3: Tabs, search and Show more.**
  - Tab counts match the seed. Sent shows 30 rows. Searching "mallory" gives 1 row, and "zzz" gives the empty message.
  - Reseed with `seed_local.py --many`, which adds 1,050 extra `sent` rows, to check that "Show more" appears, appends the remaining rows, and updates "Showing N of TOTAL".
- [ ] **Step 4: Cancel flow.**
  - Cancel the +28 min row. The dialog copy matches the spec. On confirm, the row disappears, the Cancelled count goes up, and `slack-calls.log` shows one cancellation post.
  - **Stale case:** set another pending row to `sent` with direct SQL, then click its Cancel. Expected: the "already sent" toast, no POST to `/cancel`, and the list refreshes.
- [ ] **Step 5: Bot menu.**
  - Pause gives the confirm, then the chip shows "Bot paused" and `.bot_paused` exists in the worktree.
  - Resume clears it, and `.bot_paused` is gone afterwards.
  - EOD gives the confirm, then the "Sent N follow-up(s)." toast with N equal to the number of seeded `sent` rows within 24 h and no reply. `slack-calls.log` shows the same N follow-ups.
  - Keyboard: Tab to the chip, press Enter, use the arrow keys, press Escape, and check that focus returns to the chip.
- [ ] **Step 6: Failure.** Stop the harness and click Refresh. Expected: the old data stays and the `#notice` error appears. Restart the harness and click "Try again" to recover.
- [ ] **Step 7: Dark mode and phone.**
  - Toggle the theme. After a reload it is still dark, and the login page is dark too.
  - Screenshots `after-desktop-dark.png`, `after-mobile-light.png` (390×844) and `after-mobile-dark.png`.
  - At 360 px, `document.documentElement.scrollWidth <= 360`.
- [ ] **Step 8: Empty DB.** Reseed with `--empty`. Up next shows "Nothing coming up right now." and All ETCs shows "No ETCs yet."
- [ ] **Step 9: Fix and commit.** Fix anything found, rerun Tasks 2–5 tests, and commit with the message `Polish dashboard after browser checks`. Skip the commit if there was nothing to fix.

### Task 7: Whole-branch checks, reviews, push

- [ ] **Step 1: Full suite.**
  - Run `../etc-monitor/env/bin/python -m pytest tests -o addopts="" -q -rfE --continue-on-collection-errors -p no:cacheprovider`, then compare the FAILED/ERROR list with `$SP/b.lst`.
  - Expected: no new failures, and the passed count rises by the new tests.
- [ ] **Step 2: Scope.**
  - Run `git diff --stat 04040b8`. Expected: only the allowed paths from Global Constraints.
  - Run `git diff 04040b8 -- src/database`. Expected: only the `get_pending_followups` change.
- [ ] **Step 3: Import and bot smoke test.** Run `../etc-monitor/env/bin/python -c "import src.bot.app, src.database.repositories.reminder_repository"` with placeholder env. Expected: no error.
- [ ] **Step 4: Reviews.**
  - Run the `code-review` skill on the branch diff against `04040b8`, then the `security-review` skill.
  - Fix confirmed findings, rerun Steps 1–3, and commit.
- [ ] **Step 5: Check before pushing.**
  - List `.github/workflows/*.yml` on the branch and their `on:` triggers. Report any that would run on a push to `feat/admin-login`.
  - Confirm `git rev-parse --abbrev-ref @{u}` has no upstream.
- [ ] **Step 6: Push only this branch.** Run `git push origin feat/admin-login:feat/admin-login`. Do not touch `add/test-scripts`, `main` or the server.
- [ ] **Step 7: Update the `admin-login-work` memory** with the head commit, the test counts, and the deploy notes: one bot-loaded file changes, EOD resumes at the bot's next restart, and the read-only query check on the server before merging.
