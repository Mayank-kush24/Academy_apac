/**
 * User Management JavaScript
 */

let editingUserId = null;

// Load users on page load
document.addEventListener('DOMContentLoaded', function() {
    loadUsers();
});

/**
 * Load all users
 */
async function loadUsers() {
    try {
        const response = await authenticatedFetch('/api/users');
        if (!response.ok) {
            throw new Error('Failed to load users');
        }
        
        const data = await response.json();
        renderUsersTable(data.users);
    } catch (error) {
        showError('Failed to load users: ' + error.message);
    }
}

/**
 * Render users table
 */
function renderUsersTable(users) {
    const tbody = document.getElementById('usersTableBody');
    
    if (users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center">No users found</td></tr>';
        return;
    }
    
    tbody.innerHTML = users.map(user => `
        <tr>
            <td>${escapeHtml(user.name)}</td>
            <td>${escapeHtml(user.email)}</td>
            <td><span class="badge badge-${user.role}">${user.role}</span></td>
            <td><span class="badge badge-${user.status}">${user.status}</span></td>
            <td>${formatDate(user.created_at)}</td>
            <td>
                <div class="table-actions">
                    <button class="table-action-btn table-action-btn-edit" onclick="editUser('${user.id}')" title="Edit">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="table-action-btn table-action-btn-delete" onclick="deleteUser('${user.id}')" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
}

/**
 * Open create user modal
 */
function openCreateModal() {
    editingUserId = null;
    document.getElementById('modalTitle').textContent = 'Add User';
    document.getElementById('userForm').reset();
    document.getElementById('userId').value = '';
    document.getElementById('passwordRequired').style.display = 'inline';
    document.getElementById('userPassword').required = true;
    document.getElementById('userModal').style.display = 'flex';
}

/**
 * Edit user
 */
async function editUser(userId) {
    try {
        const response = await authenticatedFetch('/api/users');
        if (!response.ok) {
            throw new Error('Failed to load users');
        }
        
        const data = await response.json();
        const user = data.users.find(u => u.id === userId);
        
        if (!user) {
            throw new Error('User not found');
        }
        
        editingUserId = userId;
        document.getElementById('modalTitle').textContent = 'Edit User';
        document.getElementById('userId').value = user.id;
        document.getElementById('userName').value = user.name;
        document.getElementById('userEmail').value = user.email;
        document.getElementById('userRole').value = user.role;
        document.getElementById('userStatus').value = user.status;
        document.getElementById('userPassword').value = '';
        document.getElementById('passwordRequired').style.display = 'none';
        document.getElementById('userPassword').required = false;
        document.getElementById('userModal').style.display = 'flex';
    } catch (error) {
        showError('Failed to load user: ' + error.message);
    }
}

/**
 * Close modal
 */
function closeModal() {
    document.getElementById('userModal').style.display = 'none';
    editingUserId = null;
}

/**
 * Handle form submission
 */
document.getElementById('userForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const formData = {
        name: document.getElementById('userName').value,
        email: document.getElementById('userEmail').value,
        role: document.getElementById('userRole').value,
        status: document.getElementById('userStatus').value
    };
    
    const password = document.getElementById('userPassword').value;
    if (password || !editingUserId) {
        formData.password = password;
    }
    
    const errorDiv = document.getElementById('formError');
    errorDiv.style.display = 'none';
    
    try {
        let response;
        if (editingUserId) {
            // Update user
            response = await authenticatedFetch(`/api/users/${editingUserId}`, {
                method: 'PUT',
                body: JSON.stringify(formData)
            });
        } else {
            // Create user
            response = await authenticatedFetch('/api/users', {
                method: 'POST',
                body: JSON.stringify(formData)
            });
        }
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Operation failed');
        }
        
        closeModal();
        loadUsers();
    } catch (error) {
        errorDiv.textContent = error.message;
        errorDiv.style.display = 'block';
    }
});

/**
 * Delete user
 */
async function deleteUser(userId) {
    if (!confirm('Are you sure you want to delete this user?')) {
        return;
    }
    
    try {
        const response = await authenticatedFetch(`/api/users/${userId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Delete failed');
        }
        
        loadUsers();
    } catch (error) {
        showError('Failed to delete user: ' + error.message);
    }
}

/**
 * Utility functions
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

function showError(message) {
    alert(message); // Can be replaced with a toast notification
}
