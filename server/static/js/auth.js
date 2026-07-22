/**
 * Authentication — CDI portal cookie only (no app JWT / password login).
 */

/** Prefix absolute app paths with WSGI SCRIPT_NAME (e.g. /apacacademy). */
function appUrl(path) {
    if (!path) return '/';
    if (path.indexOf('http://') === 0 || path.indexOf('https://') === 0) return path;
    var root = (window.__APP_SCRIPT_ROOT__ || '').replace(/\/$/, '');
    if (!root) return path;
    if (path === root || path.indexOf(root + '/') === 0) return path;
    if (path.charAt(0) !== '/') return root + '/' + path;
    return root + path;
}

document.addEventListener('DOMContentLoaded', function() {
    if (window.location.pathname !== '/login') return;
    var portalLogin = window.__CDI_PORTAL_LOGIN_URL__ || '';
    if (portalLogin) {
        window.location.replace(portalLogin);
    }
});

function doLogin() {
    var portalLogin = window.__CDI_PORTAL_LOGIN_URL__ || '';
    if (portalLogin) {
        window.location.href = portalLogin;
        return;
    }
    var errorMessage = document.getElementById('errorMessage');
    if (errorMessage) {
        errorMessage.textContent = 'Sign in through the CDI portal.';
        errorMessage.style.display = 'block';
    }
}

function initLoginForm() {
    if (window.location.pathname !== '/login') return;
    var loginForm = document.getElementById('loginForm');
    var loginBtn = document.getElementById('loginSubmitBtn');
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

function redirectByRole() {
    window.location.href = appUrl('/');
}

function getAuthToken() {
    // Auth is now driven by the CDI ``h2s_cdi_session`` cookie, not a page-issued
    // JWT in localStorage. Many legacy pages still do ``if (!token) redirect to /login``
    // and ``Authorization: Bearer ${token}`` — return a truthy sentinel so those guards
    // pass. The server ignores the bogus Bearer header when a valid cookie is present.
    return 'session';
}

function getCurrentUser() {
    var userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = appUrl('/logout');
}

async function authenticatedFetch(url, options) {
    if (options === undefined) options = {};
    var token = getAuthToken();
    var headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    if (token) {
        headers['Authorization'] = 'Bearer ' + token;
    }
    var resolved = typeof cohortApiUrl === 'function' ? cohortApiUrl(url) : url;
    var finalUrl = appUrl(resolved);
    var response = await fetch(finalUrl, Object.assign({}, options, {
        headers: headers,
        credentials: 'same-origin'
    }));
    if (response.status === 401) {
        logout();
        throw new Error('Session expired');
    }
    return response;
}
