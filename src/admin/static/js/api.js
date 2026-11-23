/* Calls to the admin API. Every call is started by the person using the page:
 * nothing here runs on a timer.
 */

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request(path, { method = 'GET' } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    });
  } catch (err) {
    throw new ApiError("Couldn't reach the server. Check your connection and try again.", 0);
  }

  if (response.status === 401) {
    // The 7-day session ended: go back to the sign-in page.
    window.location.assign('/login');
    throw new ApiError('Your session has ended. Please sign in again.', 401);
  }

  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    data = null;
  }

  if (!response.ok) {
    const message = data && typeof data.error === 'string' && data.error ? data.error : '';
    throw new ApiError(message, response.status);
  }
  return data;
}

export function getReminders({ status, limit = 1000, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (status) params.set('status', status);
  return request(`/api/reminders?${params}`);
}

export function getReminder(id) {
  return request(`/api/reminders/${encodeURIComponent(id)}`);
}

export function cancelReminder(id) {
  return request(`/api/reminders/${encodeURIComponent(id)}/cancel`, { method: 'POST' });
}

export function getBotStatus() {
  return request('/api/bot/status');
}

export function setBotPaused(paused) {
  return request(paused ? '/api/bot/pause' : '/api/bot/resume', { method: 'POST' });
}

export function runEodCheck() {
  return request('/api/reminders/trigger-eod', { method: 'POST' });
}
