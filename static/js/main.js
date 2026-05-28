document.addEventListener('DOMContentLoaded', () => {
    // 1. Dashboard Metrics Real-Time Polling
    const isDashboard = document.getElementById('dashboard-metrics-container');
    if (isDashboard) {
        setInterval(pollDashboardMetrics, 3000);
        setInterval(pollRecentAlerts, 4000);
    }

    // 2. Alert Notification Banner Polling (Global)
    const isLiveFeed = document.getElementById('live-feed-monitor');
    if (isLiveFeed) {
        setInterval(pollLiveStatusAlerts, 2000);
    }

    // 3. Client-side Search / Filtering for Tables
    setupSearchFilters();
});

// Cache for tracking the last seen alert ID to prevent duplicate alert popups
let lastSeenAlertId = 0;

/**
 * Polls Flask backend API to update KPI metrics on the dashboard dynamically.
 */
function pollDashboardMetrics() {
    fetch('/api/metrics')
        .then(response => response.json())
        .then(data => {
            updateMetricValue('metric-total-students', data.total_students);
            updateMetricValue('metric-today-entries', data.today_entries);
            updateMetricValue('metric-pending-fees', data.pending_fee_count);
            updateMetricValue('metric-total-alerts', data.total_alerts_count);
        })
        .catch(err => console.error("Error polling dashboard metrics:", err));
}

function updateMetricValue(elementId, value) {
    const el = document.getElementById(elementId);
    if (el && el.innerText !== String(value)) {
        el.style.opacity = '0.3';
        setTimeout(() => {
            el.innerText = value;
            el.style.opacity = '1';
        }, 150);
    }
}

/**
 * Polls Flask backend API for recent alerts and updates the dashboard feed.
 */
function pollRecentAlerts() {
    const container = document.getElementById('recent-alerts-list');
    if (!container) return;

    fetch('/api/recent_alerts')
        .then(response => response.json())
        .then(data => {
            if (data.alerts.length === 0) {
                container.innerHTML = '<li class="list-group-item bg-transparent text-muted border-0 ps-0">No recent alerts registered.</li>';
                return;
            }

            let html = '';
            data.alerts.forEach(alert => {
                const badgeClass = alert.message.includes('Unauthorized') ? 'bg-danger' : 'bg-warning text-dark';
                html += `
                    <li class="list-group-item bg-transparent border-bottom border-secondary ps-0 pe-0 text-light py-3 d-flex justify-content-between align-items-center">
                        <div>
                            <span class="badge ${badgeClass} me-2">${alert.message.includes('Unauthorized') ? 'ALERT' : 'WARNING'}</span>
                            <span>${alert.message}</span>
                        </div>
                        <small class="text-muted">${alert.timestamp}</small>
                    </li>
                `;
            });
            container.innerHTML = html;
        })
        .catch(err => console.error("Error polling recent alerts:", err));
}

/**
 * Polls recent alerts and flashes toast notifications on the screen during live webcam feed monitoring.
 */
function pollLiveStatusAlerts() {
    fetch('/api/recent_alerts?limit=1')
        .then(response => response.json())
        .then(data => {
            if (data.alerts && data.alerts.length > 0) {
                const latest = data.alerts[0];
                
                // If it is a new alert, show notification
                if (lastSeenAlertId !== 0 && latest.id > lastSeenAlertId) {
                    showNotificationToast(latest.message);
                }
                lastSeenAlertId = latest.id;
            }
        })
        .catch(err => console.error("Error polling live status alerts:", err));
}

/**
 * Renders a slide-in glassmorphic warning toast at the bottom right corner of the page.
 */
function showNotificationToast(message) {
    let container = document.getElementById('toast-notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-notification-container';
        container.style.position = 'fixed';
        container.style.bottom = '24px';
        container.style.right = '24px';
        container.style.zIndex = '9999';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.gap = '10px';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'glass-card alert-item-new';
    toast.style.background = 'rgba(20, 10, 10, 0.9)';
    toast.style.borderColor = '#ff453a';
    toast.style.padding = '16px 24px';
    toast.style.maxWidth = '360px';
    toast.style.transform = 'translateX(120%)';
    toast.style.transition = 'transform 0.4s cubic-bezier(0.16, 1, 0.3, 1)';
    toast.style.boxShadow = '0 10px 40px rgba(255, 69, 58, 0.2)';
    
    // Dynamic message content
    toast.innerHTML = `
        <div class="d-flex align-items-center gap-3">
            <div style="font-size: 24px; color: #ff453a;">⚠️</div>
            <div>
                <strong style="color: #ff453a; font-family: 'Outfit';">ACCESS ALERT</strong>
                <div style="font-size: 0.85rem; color: #f5f5f7; margin-top: 4px;">${message}</div>
            </div>
        </div>
    `;

    container.appendChild(toast);
    
    // Slide in
    setTimeout(() => {
        toast.style.transform = 'translateX(0)';
    }, 100);

    // Auto dismiss after 5 seconds
    setTimeout(() => {
        toast.style.transform = 'translateX(120%)';
        setTimeout(() => {
            toast.remove();
        }, 400);
    }, 5000);
}

/**
 * Triggers a boarding simulation for test and viva demonstration.
 */
function triggerSimulation(studentId) {
    const btn = document.getElementById(`sim-btn-${studentId}`);
    if (btn) {
        btn.disabled = true;
        const originalText = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Scanning...';
        
        fetch(`/simulate_entry/${studentId}`)
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    showNotificationToast(`Boarding simulated: ${data.name || studentId}`);
                }
                setTimeout(() => {
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                }, 1000);
            })
            .catch(err => {
                console.error("Simulation failed:", err);
                btn.disabled = false;
                btn.innerHTML = originalText;
            });
    }
}

/**
 * Sets up live inputs for tables to search items dynamically.
 */
function setupSearchFilters() {
    const searchInput = document.getElementById('table-search-input');
    const targetTable = document.getElementById('table-filterable');
    
    if (searchInput && targetTable) {
        searchInput.addEventListener('keyup', () => {
            const term = searchInput.value.toLowerCase().trim();
            const rows = targetTable.getElementsByTagName('tbody')[0].getElementsByTagName('tr');
            
            for (let row of rows) {
                let match = false;
                const cells = row.getElementsByTagName('td');
                
                for (let cell of cells) {
                    if (cell.textContent.toLowerCase().includes(term)) {
                        match = true;
                        break;
                    }
                }
                
                if (match) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            }
        });
    }
}
