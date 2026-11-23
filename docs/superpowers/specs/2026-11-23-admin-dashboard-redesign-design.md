# Admin dashboard redesign

Date: 2026-11-23. Branch: `feat/admin-login`, the same branch as today's login work. The owner wants all of today's changes on one branch.

## Why

The owner finds the current admin dashboard generic, "AI-generated" looking, and clumsy. The biggest annoyance is that it reloads by itself: `dashboard.js:278` runs a `setInterval` every 10 s. Each run hides the table behind "Loading reminders…", fetches 500 reminders plus the bot status, redraws the table and loses the scroll position. In one session this made 446 requests and moved 7.9 MB.

The dashboard may also be used by beginners, so everything must be **simple and obvious to use**.

What the owner opens the page for, in their own words:
- see the **upcoming ETCs at the top**;
- easily **find which ETCs are pending**.

## Goals

1. **Up next** at the top: active reminders (`pending` + `rescheduled`), soonest first, grouped by day ("Today, Monday 23 November", "Tomorrow, …", then dates). Each row shows:
   - the time the bot will post (`reminder_datetime`), plus a relative label ("in 28 min");
   - the person;
   - the channel;
   - the ETC text (`deadline_text`);
   - a **Cancel** button.
   - Show the first 10 rows, then a "Show all N pending" button.
2. **All ETCs** below:
   - tabs `All · Pending · Sent · Cancelled · Failed`, each with its count;
   - a search box that matches person, channel or ETC text;
   - a table with columns Person, Channel, ETC, Due, Status, Created, and an action (Cancel for active rows only);
   - a "Show more" button that loads older rows, so every reminder can be reached and not just the newest 500.
3. **No automatic reloading, at all.**
   - Remove every timer that fetches data.
   - Add a **Refresh** button and an "Updated 12:30" label.
   - Data loads once when the page opens, again when Refresh is pressed, and again after an action (cancel, pause/resume, EOD).
   - On Refresh the current list stays on screen while the button shows it is working. Nothing blanks out.
   - *Builder's call, flagged to the owner:* the "in 28 min" labels count down once a minute in the browser. This never contacts the server and never redraws the list.
4. **Bot controls are safer.**
   - "Pause Bot" and "Trigger EOD" move out of the header into a small menu that opens from the status chip ("Bot running ▾" / "Bot paused ▾").
   - Each menu item has a one-line plain explanation.
   - Each action asks for confirmation in a styled dialog, not `window.confirm`, that says what will happen. EOD sends follow-up messages in Slack.
   - Results appear as a short on-page message, not `alert()`.
5. **Plain, beginner-friendly wording.**
   - One helper line under each section heading. For example: "Reminders the bot will post in Slack, soonest first."
   - Buttons have text labels, not icons alone. The only exception is the theme toggle, which has a tooltip and an aria-label.
   - Cancel is always visible, not only on hover.
   - The cancel confirmation reads, roughly: "Cancel Priya Raman's reminder for 1:00 PM today? The bot won't post it, and a short 'Reminder cancelled' note will be posted in the Slack thread."
   - Every status has a text label (Pending, Sent, Cancelled, Failed, Rescheduled), never colour alone.
6. **Look: "Warm and classic" (mockup C), with a dark version.** Both were chosen and approved by the owner in the mockup viewer.
   - Light: paper background `#faf8f5`, surfaces `#fffdf9`, borders `#e7e2da`, text `#1c1917`, muted `#78716c`, accent burnt orange `#c2410c`, success `#15803d`, danger `#b42318`.
   - Dark (warm charcoal): background `#171412`, surfaces `#1c1916`/`#23201c`, borders `#2c2723`, text `#ece5da`, muted `#a39a8e`, accent `#f08a4b`, success `#6cc28a`, danger `#f19a8a`.
   - Type: a serif (`"Iowan Old Style", Charter, Georgia, serif`) for the brand, section headings and the italic day labels. The system sans stack for everything else. Tabular numbers for times.
   - Theme toggle (sun/moon) in the header. The first visit follows the system setting, and the choice is remembered under the existing `localStorage` key `theme`. The login page uses the same theme.
   - No stat cards, no gradients, no coloured icon tiles. Counts live in the tabs.
7. **Icons: Phosphor Icons (regular weight), MIT licensed,** from the official `@phosphor-icons/core` package.
   - The owner first suggested svgviewer.dev. That site turned out to be an open upload directory where each icon carries its own uploader-chosen license, so Phosphor's official source was used instead, and the owner was told.
   - Icons go in as an inline SVG sprite (`<symbol>` + `<use>`), with the MIT notice included.
   - Use icons only where they help recognition: refresh, search, cancel (x), sign out, pause/play, EOD (lightning), sun/moon, caret, warning, empty tray.
8. **The login page is restyled to match.**
   - It stays a username and password form with exactly two inputs, posting to the same `/login` route.
   - Error messages are shown the same way.
9. **Correct times.**
   - Show all times in IST (`Asia/Kolkata`) whatever the viewer's computer is set to.
   - `deadline_datetime` and `reminder_datetime` are naive IST. `created_at` is naive UTC, because it comes from the DB default `CURRENT_TIMESTAMP`. The current UI shows "Created" 5 h 30 min wrong.
   - Parse the strings by hand. Microsecond fractions don't parse reliably in every browser.
   - `sent_at` and `updated_at` are written with `datetime.now()`, in whatever zone the server clock uses, so they are **not displayed**.
10. **Security fix.** Never put API data into `innerHTML`. Today `user_name` and `channel_name` go in unescaped, which is an XSS risk from a crafted Slack display name. Build rows with DOM nodes and `textContent`.
11. **Works on a phone.**
    - Below about 720 px the header wraps.
    - Up next rows and table rows become stacked items.
    - No sideways scrolling.
12. **Clear states.**
    - First load: a quiet loading line.
    - Empty: a tray icon plus a sentence, e.g. "No pending ETCs. New ones appear here when someone gives an ETC in a Slack thread."
    - Error: an inline message with a "Try again" button. Data already shown stays visible.
    - A session that expires still redirects to `/login` through the existing 401 fetch wrapper.
13. **Past-due active reminders.** Reminders that came due while the bot was down stay `pending` forever (a known gap). Show them in their own small group at the end of Up next: "Past due (N): these were not posted, usually because the bot was offline at that time." They don't sit at the top and push real upcoming items down.

14. **Fix the EOD follow-up check (owner's decision, 2026-11-23: "fix it too").**
    - **Bug:** `ReminderRepository.get_pending_followups` (`reminder_repository.py:219`) uses SQLite's `datetime('now', '-24 hours')`. Postgres has no `datetime()` function, so on production both the bot's 19:00 IST EOD job and the admin's EOD button have failed since the move to Postgres. The last follow-up was sent on 2026-02-12.
    - **Fix (one query, nothing else):** replace that expression with a `?` parameter, `self._datetime_to_str(datetime.now() - timedelta(hours=24))`. That is the same clock and format `mark_sent` uses for `sent_at`/`reminder_sent_at`, so the comparison is right on SQLite, Postgres and MySQL whatever the server's time zone. Passing a parameter also makes `DBManager` rewrite `?`→`%s`.
    - **What it sends once fixed:** in the Slack thread, `👀 <@user> Update on this?` plus the ETC text. It goes only to reminders that are `sent`, were posted in the last 24 h, have no follow-up yet, and whose person hasn't replied since. There is no backlog flood: older reminders are outside the 24 h window. At current volume, expect about 0 to 2 per evening.
    - **When it takes effect:**
      - the admin's "Run EOD check now" works as soon as the admin restarts with the new code;
      - the bot's automatic 19:00 IST job resumes only after the bot process restarts. It restarts by itself every Sunday at 05:30 IST via logrotate, so automatic follow-ups resume within a week of deploying unless the bot is restarted sooner.
    - **Must be proven before deploy:** a unit test on SQLite, plus the same query run against a throwaway local Postgres. On the server, the new query can be run read-only (`SELECT` only) before merging.
    - **The menu keeps "Run EOD check now",** with the explanation "Posts '👀 Update on this?' in Slack for reminders sent in the last 24 hours that got no reply." It has a confirm dialog, and the result is shown as "Sent N follow-up(s)."

## Non-goals

- Any backend, API, bot, database or settings change other than the EOD query in goal 14. The frontend uses the existing endpoints exactly as they are:
  - `GET /api/reminders` (`status`, `limit` ≤ 1000, `offset`; ordered by `created_at DESC`; returns `stats` only when unfiltered);
  - `POST /api/reminders/<id>/cancel`;
  - `GET /api/bot/status`, `POST /api/bot/pause|resume`;
  - `POST /api/reminders/trigger-eod`.
- Edit or delete UI, a reminder details panel, the original Slack message text (the API doesn't return it), and links into Slack.
- Charts, stat cards and analytics.
- New dependencies, frameworks or a build step. No external font or CDN requests: the Google Fonts link is removed.

## Anti-goals: a failure even if it "works"

- Anything that reloads or polls on its own.
- Any change to how the bot runs, pauses, or messages people, other than EOD follow-ups working again exactly as designed (goal 14).
- Jargon or icon-only controls that a beginner can't understand.
- A look that again reads as a generic template: purple gradients, Inter everywhere, emoji-ish icon tiles.

## Constraints

- Production runs hundreds of live ETCs.
  - Only `src/admin/templates/*`, `src/admin/static/*`, `tests/*`, this doc, and the single EOD query in `src/database/repositories/reminder_repository.py` change.
  - The bot never imports `src/admin`.
  - The repository file *is* loaded by the bot, so that one change must be minimal and proven on SQLite and Postgres. An import or syntax error there would stop the bot at its next restart.
- `created_at` on production is naive **UTC**. Evidence from the owner's live screenshot: "20 Minutes" was created at 11:30:47 with a deadline of 17:20:47, and "5 pm" was created at 11:10:04 (16:40 IST). Convert it to IST for display; this is a fixed shift.
- **Past-due copy (builder's call).** The cause of the 22 stuck reminders is not known for certain (bot offline, or the shared job-ID gap), so the wording doesn't guess: "Past due (N): the bot didn't post these at their time. You can cancel them if they're no longer needed." On production this group is currently the whole of Up next (0 upcoming, 22 past due), so the "nothing coming up" empty state must read well above it.
- **Stale Cancel (builder's call).** Before the cancel dialog opens, re-fetch the reminder (`GET /api/reminders/<id>`). If it is no longer active, say so and refresh instead of cancelling. The cancel endpoint itself doesn't check status.
- **Loading (builder's call).** "All" loads with `limit=1000`, which covers everything in production today, so search covers every row. "Show more" (offset paging) appears only when `total` exceeds what is loaded.
- The `/login` form contract and the existing auth tests must keep passing:
  - exactly 2 `<input>`s;
  - `href="/logout"` on the dashboard.
- Plain HTML, CSS and JavaScript served by Flask, as today.
- All verification happens locally with a seeded SQLite DB and placeholder Slack tokens. Nothing touches production or real Slack.

## Approaches considered

| Approach | Trade-off | Decision |
|---|---|---|
| Rewrite the existing template, CSS and JS from scratch, same stack | No installs or build step on the server; same deploy as the login work | **Picked by the owner** |
| Move to a framework (React, Tailwind, etc.) | Needs new installs and a build step on the live server; risk with no visible gain | Rejected |
| Restyle the current page only | Keeps the clumsy layout, the polling and the XSS; doesn't put upcoming ETCs first | Rejected |

The owner picked the look in the mockup viewer from three options:

- **A** clean light;
- **B** dark;
- **C** warm and classic.

They chose **C, plus a dark version of C**, and approved the dark dashboard, the bot menu and the login page mockups. Their extra instruction: keep things simple and understandable for beginners.

## Left to the builder

- Exact spacing, font sizes, wording polish, and which icon goes in which spot within the list above.
- Page sizes for "Show more" and how tabs cache data until Refresh.
- Regression tests:
  - the dashboard must have no data-fetching timer;
  - the templates must not load external fonts;
  - the dashboard and login pages must render;
  - the auth tests keep passing.
- Browser checks with Playwright against the local server, at desktop and phone widths, in light and dark, including long ETC text, missing names and an empty list.
