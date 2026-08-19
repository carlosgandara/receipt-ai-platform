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
    // Get token from URL query string
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
// DASHBOARD PAGE
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

    // Auto-fetch protected data when page loads
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

    // Auto-fetch user info when page loads
    window.onload = fetchUserInfo;
}