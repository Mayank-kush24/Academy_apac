/**
 * Authentication JavaScript
 * Note: "runtime.lastError: The message port closed" in console is from a browser
 * extension (e.g. password manager), not this app — safe to ignore.
 */

// Check if user is already logged in (only on login page)
document.addEventListener('DOMContentLoaded', function() {
    // Only run this check on the login page
    if (window.location.pathname === '/login' || window.location.pathname === '/') {
        const token = localStorage.getItem('token');
        if (token) {
            // Verify token is still valid
            fetch('/api/auth/me', {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            })
            .then(response => {
                if (response.ok) {
                    return response.json();
                }
                throw new Error('Invalid token');
            })
            .then(data => {
                // Redirect based on role (only if on login/home page)
                redirectByRole(data.user.role);
            })
            .catch(() => {
                // Token invalid, clear it
                localStorage.removeItem('token');
                localStorage.removeItem('user');
            });
        }
    }
});

// Shared login logic (called by form submit and button click)
function doLogin() {
    const emailEl = document.getElementById('email');
    const passwordEl = document.getElementById('password');
    const errorMessage = document.getElementById('errorMessage');
    if (!emailEl || !passwordEl || !errorMessage) return;
    const email = (emailEl.value || '').trim();
    const password = passwordEl.value || '';
    errorMessage.style.display = 'none';
    errorMessage.textContent = '';
    if (!email || !password) {
        errorMessage.textContent = 'Email and password are required';
        errorMessage.style.display = 'block';
        return;
    }
    (async function() {
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const contentType = response.headers.get('content-type');
            const isJson = contentType && contentType.indexOf('application/json') !== -1;
            const data = isJson ? await response.json() : {};
            if (!response.ok) {
                throw new Error(data.error || 'Login failed');
            }
            if (!data.token || !data.user) {
                throw new Error('Invalid response from server');
            }
            localStorage.setItem('token', data.token);
            localStorage.setItem('user', JSON.stringify(data.user));
            redirectByRole(data.user.role);
        } catch (err) {
            errorMessage.textContent = err.message || 'Login failed';
            errorMessage.style.display = 'block';
        }
    })();
}

// Attach login handler: button click + form submit (Enter key) + run on load and DOMContentLoaded
function initLoginForm() {
    if (window.location.pathname !== '/login') return;
    const loginForm = document.getElementById('loginForm');
    const loginBtn = document.getElementById('loginSubmitBtn');
    if (!loginForm) return;
    function runLogin(e) {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        doLogin();
    }
    loginForm.addEventListener('submit', runLogin);
    loginForm.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); doLogin(); }
    });
    if (loginBtn) loginBtn.addEventListener('click', runLogin);
}
function runInitWhenReady() {
    try { initLoginForm(); } catch (err) { console.error('Login init error:', err); }
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', runInitWhenReady);
} else {
    runInitWhenReady();
}
window.addEventListener('load', runInitWhenReady);

/**
 * Redirect user based on their role
 */
function redirectByRole(role) {
    switch(role) {
        case 'admin':
            window.location.href = '/dashboard';
            break;
        case 'editor':
            window.location.href = '/dashboard';
            break;
        case 'viewer':
            window.location.href = '/dashboard';
            break;
        default:
            window.location.href = '/';
    }
}

/**
 * Get current auth token
 */
function getAuthToken() {
    return localStorage.getItem('token');
}

/**
 * Get current user info
 */
function getCurrentUser() {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
}

/**
 * Logout function
 */
function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
}

/**
 * Make authenticated API request
 */
async function authenticatedFetch(url, options = {}) {
    const token = getAuthToken();
    if (!token) {
        throw new Error('Not authenticated');
    }
    
    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...options.headers
    };
    
    const response = await fetch(url, {
        ...options,
        headers
    });
    
    if (response.status === 401) {
        // Token expired or invalid
        logout();
        throw new Error('Session expired');
    }
    
    return response;
}
