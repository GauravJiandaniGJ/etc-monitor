"""Flask admin panel application."""
from flask import Flask, jsonify
from flask_cors import CORS
from config.settings import Settings
from src.admin.middleware.auth_middleware import require_auth
from src.admin.routes.health_routes import health_bp
from src.admin.routes.reminder_routes import reminder_bp, init_reminder_routes
from src.utils.logger import get_logger, init_logger


logger = get_logger('AdminApp')


def create_app(settings: Settings = None) -> Flask:
    """Create and configure Flask application.

    Args:
        settings: Optional settings instance (creates new if not provided)

    Returns:
        Configured Flask application
    """
    if settings is None:
        settings = Settings()

    # Initialize logger
    init_logger(settings.log_level)
    logger.info('Creating Flask admin application')

    # Create Flask app
    app = Flask(__name__)
    app.secret_key = settings.flask_secret_key

    # Configure CORS
    CORS(app, resources={
        r"/api/*": {"origins": "*"},
        r"/health/*": {"origins": "*"}
    })

    # Initialize reminder routes
    init_reminder_routes(settings)

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(reminder_bp)

    # Root route - Dashboard UI
    @app.route('/')
    def root():
        """Dashboard UI for managing reminders."""
        dashboard_html = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETC Monitor Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .header {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .header h1 {
            color: #333;
            margin-bottom: 10px;
        }
        .header p {
            color: #666;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .stat-card h3 {
            color: #666;
            font-size: 14px;
            margin-bottom: 10px;
            text-transform: uppercase;
        }
        .stat-card .value {
            font-size: 32px;
            font-weight: bold;
            color: #667eea;
        }
        .controls {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .controls button, .controls select {
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }
        .controls button {
            background: #667eea;
            color: white;
        }
        .controls button:hover {
            background: #5568d3;
        }
        .controls select {
            background: #f5f5f5;
            border: 1px solid #ddd;
        }
        .table-container {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            overflow-x: auto;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        th {
            background: #f8f9fa;
            font-weight: 600;
            color: #333;
        }
        tr:hover {
            background: #f8f9fa;
        }
        .status {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            display: inline-block;
        }
        .status.pending { background: #fff3cd; color: #856404; }
        .status.sent { background: #d4edda; color: #155724; }
        .status.cancelled { background: #f8d7da; color: #721c24; }
        .status.failed { background: #f8d7da; color: #721c24; }
        .status.rescheduled { background: #d1ecf1; color: #0c5460; }
        .loading {
            text-align: center;
            padding: 40px;
            color: #666;
        }
        .error {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }
        .refresh-btn {
            background: #28a745;
        }
        .refresh-btn:hover {
            background: #218838;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 ETC Monitor Dashboard</h1>
            <p>Manage and monitor all ETC reminders</p>
        </div>

        <div class="stats" id="stats">
            <div class="stat-card">
                <h3>Total Reminders</h3>
                <div class="value" id="total">-</div>
            </div>
            <div class="stat-card">
                <h3>Pending</h3>
                <div class="value" id="pending">-</div>
            </div>
            <div class="stat-card">
                <h3>Sent</h3>
                <div class="value" id="sent">-</div>
            </div>
            <div class="stat-card">
                <h3>Cancelled</h3>
                <div class="value" id="cancelled">-</div>
            </div>
        </div>

        <div class="controls">
            <button onclick="loadReminders()" class="refresh-btn">🔄 Refresh</button>
            <select id="statusFilter" onchange="loadReminders()">
                <option value="">All Status</option>
                <option value="pending">Pending</option>
                <option value="sent">Sent</option>
                <option value="cancelled">Cancelled</option>
                <option value="failed">Failed</option>
                <option value="rescheduled">Rescheduled</option>
            </select>
            <select id="limitFilter" onchange="loadReminders()">
                <option value="50">Show 50</option>
                <option value="100">Show 100</option>
                <option value="200">Show 200</option>
                <option value="500">Show 500</option>
            </select>
        </div>

        <div class="table-container">
            <div id="loading" class="loading">Loading reminders...</div>
            <div id="error" class="error" style="display:none;"></div>
            <table id="remindersTable" style="display:none;">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>User</th>
                        <th>Channel</th>
                        <th>Deadline</th>
                        <th>Reminder Time</th>
                        <th>Status</th>
                        <th>Created</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="remindersBody">
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // Get or prompt for credentials
        function getAuthHeader() {
            let username = sessionStorage.getItem('admin_username');
            let password = sessionStorage.getItem('admin_password');

            if (!username || !password) {
                username = prompt('Username:');
                if (!username) {
                    throw new Error('Username is required');
                }
                password = prompt('Password:');
                if (!password) {
                    throw new Error('Password is required');
                }
                sessionStorage.setItem('admin_username', username);
                sessionStorage.setItem('admin_password', password);
            }

            return 'Basic ' + btoa(username + ':' + password);
        }

        let authHeader = null;
        try {
            authHeader = getAuthHeader();
        } catch (e) {
            alert('Authentication required. Please refresh and enter credentials.');
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

        function escapeHtml(text) {
            if (text == null) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function getStatusClass(status) {
            return status ? status.toLowerCase() : 'pending';
        }

        function loadReminders() {
            if (!authHeader) {
                try {
                    authHeader = getAuthHeader();
                } catch (e) {
                    document.getElementById('error').style.display = 'block';
                    document.getElementById('error').textContent = 'Error: Authentication required. Please refresh the page.';
                    return;
                }
            }

            const statusFilter = document.getElementById('statusFilter').value;
            const limit = document.getElementById('limitFilter').value;

            document.getElementById('loading').style.display = 'block';
            document.getElementById('error').style.display = 'none';
            document.getElementById('remindersTable').style.display = 'none';

            let url = '/api/reminders?limit=' + encodeURIComponent(limit);
            if (statusFilter) {
                url += '&status=' + encodeURIComponent(statusFilter);
            }

            fetch(url, {
                headers: {
                    'Authorization': authHeader
                }
            })
            .then(response => {
                if (!response.ok) {
                    if (response.status === 401) {
                        sessionStorage.removeItem('admin_username');
                        sessionStorage.removeItem('admin_password');
                        authHeader = null;
                        try {
                            authHeader = getAuthHeader();
                            return loadReminders();
                        } catch (e) {
                            throw new Error('Authentication failed');
                        }
                    }
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
                    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:#666;">No reminders found</td></tr>';
                    updateStats({total: 0, pending: 0, sent: 0, cancelled: 0});
                    return;
                }

                data.reminders.forEach(reminder => {
                    const row = document.createElement('tr');
                    const reminderId = reminder.id || 0;
                    const status = reminder.status || 'pending';
                    const statusClass = getStatusClass(status);

                    // Create cells safely to prevent XSS
                    const idCell = document.createElement('td');
                    idCell.textContent = reminderId || '-';

                    const userCell = document.createElement('td');
                    userCell.textContent = reminder.user_id || '-';

                    const channelCell = document.createElement('td');
                    channelCell.textContent = reminder.channel_id || '-';

                    const deadlineCell = document.createElement('td');
                    deadlineCell.textContent = formatDate(reminder.deadline_datetime);

                    const reminderTimeCell = document.createElement('td');
                    reminderTimeCell.textContent = formatDate(reminder.reminder_datetime);

                    const statusCell = document.createElement('td');
                    const statusSpan = document.createElement('span');
                    statusSpan.className = 'status ' + statusClass;
                    statusSpan.textContent = status;
                    statusCell.appendChild(statusSpan);

                    const createdCell = document.createElement('td');
                    createdCell.textContent = formatDate(reminder.created_at);

                    const actionsCell = document.createElement('td');
                    const viewBtn = document.createElement('button');
                    viewBtn.textContent = 'View';
                    viewBtn.style.cssText = 'padding:5px 10px;background:#667eea;color:white;border:none;border-radius:3px;cursor:pointer;';
                    viewBtn.onclick = () => viewDetails(reminderId);
                    actionsCell.appendChild(viewBtn);

                    if (status === 'pending') {
                        const cancelBtn = document.createElement('button');
                        cancelBtn.textContent = 'Cancel';
                        cancelBtn.style.cssText = 'padding:5px 10px;background:#dc3545;color:white;border:none;border-radius:3px;cursor:pointer;margin-left:5px;';
                        cancelBtn.onclick = () => cancelReminder(reminderId);
                        actionsCell.appendChild(cancelBtn);
                    }

                    row.appendChild(idCell);
                    row.appendChild(userCell);
                    row.appendChild(channelCell);
                    row.appendChild(deadlineCell);
                    row.appendChild(reminderTimeCell);
                    row.appendChild(statusCell);
                    row.appendChild(createdCell);
                    row.appendChild(actionsCell);

                    tbody.appendChild(row);
                });

                updateStats(data);
            })
            .catch(error => {
                document.getElementById('loading').style.display = 'none';
                document.getElementById('error').style.display = 'block';
                document.getElementById('error').textContent = 'Error: ' + error.message;
            });
        }

        function updateStats(data) {
            // Use total from API response if available, otherwise count filtered results
            const reminders = data.reminders || [];
            const stats = {
                total: data.total !== undefined ? data.total : reminders.length,
                pending: reminders.filter(r => (r.status || '').toLowerCase() === 'pending').length,
                sent: reminders.filter(r => (r.status || '').toLowerCase() === 'sent').length,
                cancelled: reminders.filter(r => (r.status || '').toLowerCase() === 'cancelled').length
            };

            document.getElementById('total').textContent = stats.total;
            document.getElementById('pending').textContent = stats.pending;
            document.getElementById('sent').textContent = stats.sent;
            document.getElementById('cancelled').textContent = stats.cancelled;
        }

        function viewDetails(id) {
            if (!authHeader) {
                alert('Authentication required');
                return;
            }

            fetch('/api/reminders/' + encodeURIComponent(id), {
                headers: {
                    'Authorization': authHeader
                }
            })
            .then(response => {
                if (!response.ok) {
                    if (response.status === 401) {
                        sessionStorage.removeItem('admin_username');
                        sessionStorage.removeItem('admin_password');
                        authHeader = null;
                        alert('Authentication expired. Please refresh the page.');
                        return;
                    }
                    return response.json().then(err => {
                        throw new Error(err.error || 'Failed to load reminder');
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data) {
                    alert('Reminder Details:\\n\\n' + JSON.stringify(data, null, 2));
                }
            })
            .catch(error => {
                alert('Error loading details: ' + (error.message || 'Unknown error'));
            });
        }

        function cancelReminder(id) {
            if (!authHeader) {
                alert('Authentication required');
                return;
            }

            if (!confirm('Are you sure you want to cancel this reminder?')) return;

            fetch('/api/reminders/' + encodeURIComponent(id) + '/cancel', {
                method: 'POST',
                headers: {
                    'Authorization': authHeader
                }
            })
            .then(response => {
                if (!response.ok) {
                    if (response.status === 401) {
                        sessionStorage.removeItem('admin_username');
                        sessionStorage.removeItem('admin_password');
                        authHeader = null;
                        alert('Authentication expired. Please refresh the page.');
                        return;
                    }
                    return response.json().then(err => {
                        throw new Error(err.error || 'Failed to cancel reminder');
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data) {
                    alert('Reminder cancelled successfully');
                    loadReminders();
                }
            })
            .catch(error => {
                alert('Error cancelling reminder: ' + (error.message || 'Unknown error'));
            });
        }

        // Load on page load (only if auth is available)
        if (authHeader) {
            loadReminders();
            // Auto-refresh every 30 seconds
            setInterval(loadReminders, 30000);
        } else {
            document.getElementById('loading').style.display = 'none';
            document.getElementById('error').style.display = 'block';
            document.getElementById('error').textContent = 'Please refresh the page and enter your credentials to access the dashboard.';
        }
    </script>
</body>
</html>
        '''
        return dashboard_html, 200, {'Content-Type': 'text/html; charset=utf-8'}

    # Apply authentication to reminder routes
    auth_decorator = require_auth(settings)

    # Protect reminder routes with authentication
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith('/api/'):
            view_func = app.view_functions[rule.endpoint]
            app.view_functions[rule.endpoint] = auth_decorator(view_func)

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 errors."""
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        logger.error(f'Internal server error: {error}', exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

    @app.errorhandler(401)
    def unauthorized(error):
        """Handle 401 errors."""
        return jsonify({'error': 'Unauthorized'}), 401

    logger.success('Flask admin application created')

    return app


def main():
    """Main entry point for admin panel."""
    try:
        # Load settings
        settings = Settings()

        # Create app
        app = create_app(settings)

        # Get port from environment or default
        import os
        port = int(os.environ.get('ADMIN_PORT', 5000))
        debug = settings.debug

        logger.info(f'Starting admin panel on port {port} (debug={debug})')

        # Run app
        app.run(host='0.0.0.0', port=port, debug=debug)

    except Exception as e:
        logger.error(f'Fatal error starting admin panel: {e}', exc_info=True)
        raise


if __name__ == "__main__":
    main()
