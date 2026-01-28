/**
 * Authentication JavaScript
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

// Handle login form submission
const loginForm = document.getElementById('loginForm');
if (loginForm) {
    loginForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const errorMessage = document.getElementById('errorMessage');
        
        // Clear previous errors
        errorMessage.style.display = 'none';
        errorMessage.textContent = '';
        
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email, password })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Login failed');
            }
            
            // Store token and user info
            localStorage.setItem('token', data.token);
            localStorage.setItem('user', JSON.stringify(data.user));
            
            // Redirect based on role
            redirectByRole(data.user.role);
            
        } catch (error) {
            errorMessage.textContent = error.message;
            errorMessage.style.display = 'block';
        }
    });
}

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
