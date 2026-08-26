// ============================================================
// COMMON UTILITIES
// ============================================================

/**
 * Authenticated fetch - automatically handles 401 errors
 * by calling /refresh and retrying the request.
 */
async function authenticatedFetch(url, options = {}) {
    let response = await fetch(url, options);
    
    if (response.status === 401) {
        const toast = document.getElementById('toast');
        if (toast) {
            toast.textContent = '⏳ Refreshing session...';
            toast.className = 'show';
        }
        
        const refreshResponse = await fetch('/refresh', { method: 'POST' });
        if (refreshResponse.ok) {
            if (toast) {
                toast.textContent = '✅ Session refreshed silently!';
                setTimeout(() => { toast.className = ''; }, 2000);
            }
            response = await fetch(url, options);
        } else {
            window.location.href = '/login';
        }
    }
    return response;
}

/**
 * Logout - calls /logout and redirects to login page.
 */
async function logout() {
    await fetch('/logout', { method: 'POST' });
    window.location.href = '/login';
}


// ============================================================
// LOGIN PAGE
// ============================================================

if (document.getElementById('login-form')) {
    document.getElementById('login-form').onsubmit = async (e) => {
        e.preventDefault();
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const msg = document.getElementById('msg');
        
        msg.textContent = 'Logging in...';
        msg.className = '';

        try {
            const res = await fetch('/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();

            if (res.ok) {
                msg.className = 'success';
                msg.textContent = '✅ Login successful! Redirecting...';
                setTimeout(() => window.location.href = '/dashboard', 800);
            } else {
                msg.className = 'error';
                msg.textContent = data.error || 'Login failed';
            }
        } catch (err) {
            msg.className = 'error';
            msg.textContent = 'Network error: ' + err.message;
        }
    };
}


// ============================================================
// REGISTER PAGE
// ============================================================

if (document.getElementById('register-form')) {
    document.getElementById('register-form').onsubmit = async (e) => {
        e.preventDefault();
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const msg = document.getElementById('msg');

        try {
            const res = await fetch('/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();

            if (res.ok) {
                msg.className = 'success';
                msg.textContent = data.message;
            } else {
                msg.className = 'error';
                msg.textContent = data.error || 'Register failed';
            }
        } catch (err) {
            msg.className = 'error';
            msg.textContent = 'Network error: ' + err.message;
        }
    };
}


// ============================================================
// FORGOT PASSWORD PAGE
// ============================================================

if (document.getElementById('forgot-password-form')) {
    document.getElementById('forgot-password-form').onsubmit = async (e) => {
        e.preventDefault();
        const email = document.getElementById('email').value;
        const msg = document.getElementById('msg');

        try {
            const res = await fetch('/forgot-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });
            const data = await res.json();

            msg.className = 'success';
            msg.textContent = data.message;
        } catch (err) {
            msg.className = 'error';
            msg.textContent = 'Network error: ' + err.message;
        }
    };
}


// ============================================================
// RESET PASSWORD PAGE
// ============================================================

if (document.getElementById('reset-password-form')) {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');

    document.getElementById('reset-password-form').onsubmit = async (e) => {
        e.preventDefault();
        const new_password = document.getElementById('new_password').value;
        const msg = document.getElementById('msg');

        if (!token) {
            msg.className = 'error';
            msg.textContent = 'Missing reset token. Please use the link from your email.';
            return;
        }

        try {
            const res = await fetch('/reset-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, new_password })
            });
            const data = await res.json();

            if (res.ok) {
                msg.className = 'success';
                msg.textContent = data.message;
            } else {
                msg.className = 'error';
                msg.textContent = data.error || 'Reset failed';
            }
        } catch (err) {
            msg.className = 'error';
            msg.textContent = 'Network error: ' + err.message;
        }
    };
}


// ============================================================
// DASHBOARD PAGE (Legacy protected data display – keep for compatibility)
// ============================================================

if (document.getElementById('api-response')) {
    async function fetchProtectedData() {
        const pre = document.getElementById('api-response');
        pre.textContent = 'Fetching...';
        try {
            const response = await authenticatedFetch('/protected');
            const data = await response.json();
            pre.textContent = JSON.stringify(data, null, 2);
        } catch (error) {
            pre.textContent = 'Error: ' + error.message;
        }
    }

    window.onload = fetchProtectedData;
}


// ============================================================
// PROFILE PAGE
// ============================================================

if (document.getElementById('user-email')) {
    async function fetchUserInfo() {
        try {
            const response = await authenticatedFetch('/protected');
            const data = await response.json();
            document.getElementById('user-email').textContent = '👤 ' + data.message;
        } catch (error) {
            document.getElementById('user-email').textContent = 'Error loading profile';
        }
    }

    window.onload = fetchUserInfo;
}


// ============================================================
// PROCESSING PAGE – Poll /status/<token> and redirect
// ============================================================

(function() {
    const tokenElement = document.getElementById('processing-token');
    if (!tokenElement) return;

    const token = tokenElement.textContent.trim();
    let attempts = 0;
    const maxAttempts = 30;
    const statusEl = document.getElementById('status');
    const errorEl = document.getElementById('error');
    const debugEl = document.getElementById('debug');

    function checkStatus() {
        attempts++;
        if (debugEl) debugEl.textContent = `Checking status (attempt ${attempts})...`;

        fetch(`/status/${token}`)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                if (debugEl) debugEl.textContent += ` Got: ${JSON.stringify(data)}`;
                console.log('Status data:', data);

                if (data.status === 'complete') {
                    if (statusEl) {
                        statusEl.textContent = '✅ AI complete! Redirecting...';
                        statusEl.style.color = 'green';
                    }
                    window.location.href = data.redirect;
                } else if (data.status === 'duplicate') {
                    window.location.href = data.redirect;
                } else if (data.status === 'error') {
                    if (statusEl) statusEl.textContent = '❌ Error processing receipt.';
                    if (errorEl) {
                        errorEl.textContent = data.error || 'Unknown error';
                        errorEl.className = 'error show';
                    }
                } else {
                    if (statusEl) statusEl.textContent = `Processing... (${attempts})`;
                    if (attempts < maxAttempts) {
                        setTimeout(checkStatus, 3000);
                    } else {
                        if (statusEl) statusEl.textContent = '⏰ Taking longer than expected.';
                        if (errorEl) {
                            errorEl.innerHTML = 'You can try going to the review page manually: <a href="/review/' + token + '">Click here</a>';
                            errorEl.className = 'error show';
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Fetch error:', error);
                if (debugEl) debugEl.textContent += ` Error: ${error.message}`;
                setTimeout(checkStatus, 5000);
            });
    }

    setTimeout(checkStatus, 2000);
})();


// ============================================================
// DASHBOARD – Render Charts (robust destroy)
// ============================================================

(function() {
    const chartDataElement = document.getElementById('chart-data');
    if (!chartDataElement) return;

    let chartData;
    try {
        chartData = JSON.parse(chartDataElement.textContent);
    } catch (e) {
        console.error('Failed to parse chart data', e);
        return;
    }

    const barCanvas = document.getElementById('barChart');
    const lineCanvas = document.getElementById('lineChart');

    // Destroy any existing chart attached to the canvas (internal Chart.js reference)
    if (barCanvas._chart) {
        barCanvas._chart.destroy();
        barCanvas._chart = null;
    }
    if (lineCanvas._chart) {
        lineCanvas._chart.destroy();
        lineCanvas._chart = null;
    }

    // Also clear global references if they exist
    if (window.barChartInstance) {
        window.barChartInstance.destroy();
        window.barChartInstance = null;
    }
    if (window.lineChartInstance) {
        window.lineChartInstance.destroy();
        window.lineChartInstance = null;
    }

    // --- Bar chart ---
    const ctx1 = barCanvas.getContext('2d');
    const barChart = new Chart(ctx1, {
        type: 'bar',
        data: {
            labels: chartData.categories,
            datasets: [{
                label: 'Spending by Category',
                data: chartData.cat_values,
                backgroundColor: 'rgba(54, 162, 235, 0.6)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } }
        }
    });
    barCanvas._chart = barChart;
    window.barChartInstance = barChart;

    // --- Line chart ---
    const ctx2 = lineCanvas.getContext('2d');
    const lineChart = new Chart(ctx2, {
        type: 'line',
        data: {
            labels: chartData.dates,
            datasets: [{
                label: 'Weekly Spending',
                data: chartData.weekly_totals,
                fill: false,
                borderColor: 'rgba(255, 99, 132, 1)',
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } }
        }
    });
    lineCanvas._chart = lineChart;
    window.lineChartInstance = lineChart;
})();


// ============================================================
// BIND LOGOUT BUTTON (CSP‑safe, no inline onclick)
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    const btn = document.getElementById('logout-btn');
    if (btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            logout();
        });
    } else {
        console.warn('Logout button (#logout-btn) not found in DOM');
    }
});