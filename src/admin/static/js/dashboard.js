/* ETC Monitor Dashboard JavaScript */

let allReminders = [];
let currentTab = 'all';

function getSystemTheme() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    const icon = document.getElementById('theme-icon');
    if (theme === 'dark') {
        icon.innerHTML = '<path d="M12 2a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0V3a1 1 0 0 1 1-1zm7.071 2.929a1 1 0 0 1 0 1.414l-.707.707a1 1 0 1 1-1.414-1.414l.707-.707a1 1 0 0 1 1.414 0zm-14.142 0a1 1 0 0 1 1.414 0l.707.707A1 1 0 0 1 5.636 7.05l-.707-.707a1 1 0 0 1 0-1.414zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm-6 4a6 6 0 1 1 12 0 6 6 0 0 1-12 0zm-4 0a1 1 0 0 1 1-1h1a1 1 0 1 1 0 2H3a1 1 0 0 1-1-1zm17 0a1 1 0 0 1 1-1h1a1 1 0 1 1 0 2h-1a1 1 0 0 1-1-1zM5.636 16.95a1 1 0 0 1 1.414 1.414l-.707.707a1 1 0 0 1-1.414-1.414l.707-.707zm11.314 1.414a1 1 0 0 1 1.414-1.414l.707.707a1 1 0 0 1-1.414 1.414l-.707-.707zM12 19a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1z" fill="currentColor"/>';
    } else {
        icon.innerHTML = '<path d="M10.41 13.28C7.332 10.205 6.716 5.693 8.357 2c-1.23.41-2.256 1.23-3.281 2.256a10.399 10.399 0 0 0 0 14.768c4.102 4.102 10.46 3.897 14.562-.205 1.026-1.026 1.846-2.051 2.256-3.282-3.896 1.436-8.409.82-11.486-2.256Z" fill="currentColor" fill-opacity=".16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>';
    }
}

function toggleTheme() {
    const current = localStorage.getItem('theme') || getSystemTheme();
    setTheme(current === 'dark' ? 'light' : 'dark');
}

function showTab(tabName) {
    currentTab = tabName;
    document.getElementById('all-tab').style.display = tabName === 'all' ? 'block' : 'none';
    document.getElementById('pending-tab').style.display = tabName === 'pending' ? 'block' : 'none';
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    if (tabName === 'pending') {
        loadPendingReminders();
    } else {
        loadReminders();
    }
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    try {
        const date = new Date(dateStr);
        if (isNaN(date.getTime())) return '-';
        return date.toLocaleString();
    } catch (e) {
        return '-';
    }
}

function getUserInitial(userId, userName) {
    if (userName && userName !== '-' && userName !== userId) {
        return userName.charAt(0).toUpperCase();
    }
    if (userId && userId !== '-') {
        return userId.charAt(0).toUpperCase();
    }
    return '?';
}

function formatUserName(reminder) {
    if (reminder.user_name && reminder.user_name !== reminder.user_id && reminder.user_name !== '-') {
        return reminder.user_name;
    }
    if (reminder.user_id && reminder.user_id !== '-') {
        return reminder.user_id;
    }
    return '-';
}

function formatChannelName(reminder) {
    let channelName = reminder.channel_name || reminder.channel_id || '-';
    if (channelName.startsWith('#')) {
        channelName = channelName.substring(1);
    }
    return channelName;
}

function escapeHtml(text) {
    return text.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function createReminderRow(reminder) {
    const row = document.createElement('tr');
    const status = reminder.status || 'pending';
    const statusClass = status.toLowerCase();

    const messageText = reminder.deadline_text || '-';
    const escapedMessage = escapeHtml(messageText);
    const userName = formatUserName(reminder);
    const channelName = formatChannelName(reminder);
    row.innerHTML = `
        <td>
            <div class="user-badge">
                <div class="user-avatar">${getUserInitial(reminder.user_id, reminder.user_name)}</div>
                <span>${userName}</span>
            </div>
        </td>
        <td><span>#${channelName}</span></td>
        <td><div class="message-preview" title="${escapedMessage}">${escapedMessage.substring(0, 40)}${messageText.length > 40 ? '...' : ''}</div></td>
        <td><span class="time-stamp">${formatDate(reminder.deadline_datetime)}</span></td>
        <td><span class="time-stamp">${formatDate(reminder.reminder_datetime)}</span></td>
        <td>
            <span class="status-badge ${statusClass}">
                <span class="status-dot ${statusClass}"></span>
                ${status}
            </span>
        </td>
        <td><span class="time-stamp">${formatDate(reminder.created_at)}</span></td>
        <td>
            <div class="action-buttons">
                ${status === 'pending' ? `<button class="btn btn-warning" onclick="cancelReminder(${reminder.id})">Cancel</button>` : ''}
            </div>
        </td>
    `;
    return row;
}

function loadReminders() {
    document.getElementById('loading').style.display = 'block';
    document.getElementById('error').style.display = 'none';
    document.getElementById('remindersTable').style.display = 'none';

    fetch('/api/reminders?limit=500')
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => {
                throw new Error(err.error || 'Failed to load reminders');
            }).catch(() => {
                throw new Error('Failed to load reminders (HTTP ' + response.status + ')');
            });
        }
        return response.json();
    })
    .then(data => {
        document.getElementById('loading').style.display = 'none';
        document.getElementById('remindersTable').style.display = 'table';

        const tbody = document.getElementById('remindersBody');
        tbody.innerHTML = '';

        if (!data.reminders || data.reminders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-muted);">No reminders found</td></tr>';
            updateStats({total: 0, pending: 0, sent: 0, cancelled: 0});
            return;
        }

        allReminders = data.reminders;
        data.reminders.forEach(reminder => {
            tbody.appendChild(createReminderRow(reminder));
        });

        updateStats(data);
    })
    .catch(error => {
        document.getElementById('loading').style.display = 'none';
        document.getElementById('error').style.display = 'block';
        document.getElementById('error').textContent = 'Error: ' + error.message;
    });
}

function loadPendingReminders() {
    document.getElementById('loading-pending').style.display = 'block';
    document.getElementById('pendingTable').style.display = 'none';

    fetch('/api/reminders?status=pending&limit=500')
    .then(response => response.json())
    .then(data => {
        document.getElementById('loading-pending').style.display = 'none';
        document.getElementById('pendingTable').style.display = 'table';

        const tbody = document.getElementById('pendingBody');
        tbody.innerHTML = '';

        if (!data.reminders || data.reminders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;color:var(--text-muted);">No pending reminders</td></tr>';
            return;
        }

        data.reminders.forEach(reminder => {
            const row = document.createElement('tr');
            const messageText = reminder.deadline_text || '-';
            const escapedMessage = escapeHtml(messageText);
            const userName = formatUserName(reminder);
            const channelName = formatChannelName(reminder);
            row.innerHTML = `
                <td>
                    <div class="user-badge">
                        <div class="user-avatar">${getUserInitial(reminder.user_id, reminder.user_name)}</div>
                        <span>${userName}</span>
                    </div>
                </td>
                <td><span>#${channelName}</span></td>
                <td><div class="message-preview" title="${escapedMessage}">${escapedMessage.substring(0, 40)}${messageText.length > 40 ? '...' : ''}</div></td>
                <td><span class="time-stamp">${formatDate(reminder.deadline_datetime)}</span></td>
                <td><span class="time-stamp">${formatDate(reminder.reminder_datetime)}</span></td>
                <td><span class="time-stamp">${formatDate(reminder.created_at)}</span></td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-warning" onclick="cancelReminder(${reminder.id})">Cancel</button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    })
    .catch(error => {
        document.getElementById('loading-pending').style.display = 'none';
        console.error('Error loading pending reminders:', error);
    });
}

function updateStats(data) {
    if (data.stats) {
        document.getElementById('total').textContent = data.total || 0;
        document.getElementById('pending').textContent = data.stats.pending || 0;
        document.getElementById('sent').textContent = data.stats.sent || 0;
        document.getElementById('cancelled').textContent = (data.stats.cancelled || 0) + (data.stats.failed || 0);
    } else {
        const reminders = data.reminders || [];
        const stats = {
            total: data.total !== undefined ? data.total : reminders.length,
            pending: reminders.filter(r => (r.status || '').toLowerCase() === 'pending').length,
            sent: reminders.filter(r => (r.status || '').toLowerCase() === 'sent').length,
            cancelled: reminders.filter(r => (r.status || '').toLowerCase() === 'cancelled').length,
            failed: reminders.filter(r => (r.status || '').toLowerCase() === 'failed').length
        };
        document.getElementById('total').textContent = stats.total;
        document.getElementById('pending').textContent = stats.pending;
        document.getElementById('sent').textContent = stats.sent;
        document.getElementById('cancelled').textContent = stats.cancelled + stats.failed;
    }
}

function cancelReminder(id) {
    if (!confirm('Are you sure you want to cancel this reminder?')) return;

    fetch('/api/reminders/' + encodeURIComponent(id) + '/cancel', {
        method: 'POST'
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => {
                throw new Error(err.error || 'Failed to cancel reminder');
            });
        }
        return response.json();
    })
    .then(data => {
        alert('Reminder cancelled successfully');
        if (currentTab === 'pending') {
            loadPendingReminders();
        } else {
            loadReminders();
        }
    })
    .catch(error => {
        alert('Error cancelling reminder: ' + (error.message || 'Unknown error'));
    });
}

// Initialize theme
const storedTheme = localStorage.getItem('theme') || getSystemTheme();
setTheme(storedTheme);

// Load on page load
loadReminders();

// Auto-refresh every 10 seconds
setInterval(() => {
    if (currentTab === 'all') loadReminders();
    else loadPendingReminders();
}, 10000);
