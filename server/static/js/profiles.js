/**
 * User Profiles JavaScript
 */

let currentPage = 1;
let perPage = 20;
let totalPages = 1;
let filterOptions = {};
let currentFilters = {};

// Helper function for authenticated requests (fallback if auth.js not loaded)
function authenticatedFetch(url, options = {}) {
    const token = localStorage.getItem('token');
    if (!token) {
        return Promise.reject(new Error('Not authenticated'));
    }
    
    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...(options.headers || {})
    };
    
    return fetch(url, {
        ...options,
        headers
    }).then(response => {
        if (response.status === 401) {
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            window.location.href = '/login';
            throw new Error('Session expired');
        }
        return response;
    });
}

// Make it globally available
window.authenticatedFetch = authenticatedFetch;

// Helper functions (must be defined before use)
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    if (!dateString) return null;
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    } catch (e) {
        return dateString;
    }
}

function formatDateTime(dateString) {
    if (!dateString) return null;
    try {
        const date = new Date(dateString);
        return date.toLocaleString('en-US', { 
            year: 'numeric', 
            month: 'long', 
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return dateString;
    }
}

/**
 * Load and render activity logs for a profile into #profileActivityLogList
 */
async function loadProfileLogs(profileId) {
    const container = document.getElementById('profileActivityLogList');
    if (!container) return;
    const token = localStorage.getItem('token');
    if (!token) {
        container.innerHTML = '<p class="activity-log-empty">Sign in to view activity log.</p>';
        return;
    }
    try {
        const response = await fetch(`/api/profiles/${profileId}/logs?per_page=20`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) {
            container.innerHTML = '<p class="activity-log-empty">Unable to load activity log.</p>';
            return;
        }
        const data = await response.json();
        const logs = data.logs || [];
        if (logs.length === 0) {
            container.innerHTML = '<p class="activity-log-empty">No activity recorded yet for this profile.</p>';
            return;
        }
        container.innerHTML = logs.map(log => {
            const time = formatDateTime(log.created_at) || log.created_at;
            const actionClass = log.action === 'create' ? 'log-create' : log.action === 'update' ? 'log-update' : 'log-delete';
            const actionLabel = log.action === 'create' ? 'Created' : log.action === 'update' ? 'Updated' : 'Deleted';
            let changesHtml = '';
            if (log.action === 'update' && log.changes && log.changes.length > 0) {
                changesHtml = '<ul class="activity-log-changes">' + log.changes.map(c => 
                    `<li><strong>${escapeHtml(c.field)}</strong>: ${escapeHtml(String(c.old_value ?? ''))} → ${escapeHtml(String(c.new_value ?? ''))}</li>`
                ).join('') + '</ul>';
            }
            const summary = escapeHtml(log.summary || actionLabel);
            return `<div class="activity-log-item ${actionClass}">
                <div class="activity-log-header">
                    <span class="activity-log-badge">${actionLabel}</span>
                    <span class="activity-log-time">${time}</span>
                </div>
                <div class="activity-log-summary">${summary}</div>
                ${changesHtml}
            </div>`;
        }).join('');
    } catch (e) {
        container.innerHTML = '<p class="activity-log-empty">Failed to load activity log.</p>';
    }
}

// Make functions globally available immediately (before DOMContentLoaded)
window.viewProfileDetails = function(profileId) {
    console.log('viewProfileDetails called with ID:', profileId);
    
    // Get token
    const token = localStorage.getItem('token');
    if (!token) {
        alert('Please login to view profile details');
        window.location.href = '/login';
        return;
    }
    
    const url = `/api/profiles/${profileId}`;
    console.log('Fetching profile from:', url);
    
    // Make authenticated request
    console.log('Starting fetch request...');
    fetch(url, {
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        }
    })
    .then(response => {
        console.log('Fetch completed, response received');
        console.log('Response status:', response.status, response.statusText);
        console.log('Response headers:', response.headers);
        
        if (response.status === 401) {
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            window.location.href = '/login';
            return Promise.reject(new Error('Session expired'));
        }
        
        if (!response.ok) {
            console.error('Response not OK, status:', response.status);
            return response.text().then(text => {
                console.error('Error response text:', text);
                try {
                    const errorData = JSON.parse(text);
                    throw new Error(errorData.error || `Failed to load profile details (${response.status})`);
                } catch (e) {
                    throw new Error(`Failed to load profile details (${response.status}): ${text}`);
                }
            });
        }
        
        console.log('Response OK, parsing JSON...');
        return response.json().then(data => {
            console.log('JSON parsed successfully:', data);
            return data;
        }).catch(e => {
            console.error('JSON parse error:', e);
            return response.text().then(text => {
                console.error('Response text:', text);
                throw new Error('Invalid JSON response: ' + text.substring(0, 100));
            });
        });
    })
    .then(data => {
        console.log('Response data received:', data);
        
        const profile = data.profile;
        
        if (!profile) {
            console.error('No profile in response:', data);
            throw new Error('Profile not found in response');
        }
        
        console.log('Profile data:', profile);
        
        // Populate modal
        const modalNameEl = document.getElementById('modalProfileName');
        if (modalNameEl) {
            modalNameEl.textContent = profile.name || 'Profile Details';
        } else {
            console.error('Modal name element not found');
        }
        
        const modalBody = document.getElementById('profileModalBody');
        if (!modalBody) {
            console.error('Modal body element not found');
            alert('Modal not found. Please refresh the page.');
            return;
        }
        
        console.log('Populating modal body...');
        modalBody.innerHTML = `
            <div class="profile-detail-grid">
                <div class="detail-section">
                    <h4><i class="fas fa-info-circle"></i> Basic Information</h4>
                    <div class="detail-row">
                        <span class="detail-label">Name:</span>
                        <span class="detail-value">${escapeHtml(profile.name || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Email:</span>
                        <span class="detail-value">${escapeHtml(profile.email || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Mobile:</span>
                        <span class="detail-value">${escapeHtml(profile.mobile_number || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Date of Birth:</span>
                        <span class="detail-value">${formatDate(profile.date_of_birth) || 'N/A'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Gender:</span>
                        <span class="detail-value">${escapeHtml(profile.gender || 'N/A')}</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h4><i class="fas fa-briefcase"></i> Professional</h4>
                    <div class="detail-row">
                        <span class="detail-label">Organization:</span>
                        <span class="detail-value">${escapeHtml(profile.organization_name || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">BOB match:</span>
                        <span class="detail-value">${profile.bob_match ? 'Yes' : 'No'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Designation:</span>
                        <span class="detail-value">${escapeHtml(profile.designation || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Occupation:</span>
                        <span class="detail-value">${escapeHtml(profile.occupation || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Domain:</span>
                        <span class="detail-value">${escapeHtml(profile.domain || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">UTM medium:</span>
                        <span class="detail-value">${escapeHtml(profile.utm_medium || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Class Stream:</span>
                        <span class="detail-value">${escapeHtml(profile.class_stream || 'N/A')}</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h4><i class="fas fa-map-marker-alt"></i> Location</h4>
                    <div class="detail-row">
                        <span class="detail-label">Country:</span>
                        <span class="detail-value">${escapeHtml(profile.country || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">State:</span>
                        <span class="detail-value">${escapeHtml(profile.state || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">City:</span>
                        <span class="detail-value">${escapeHtml(profile.city || 'N/A')}</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h4><i class="fas fa-link"></i> Social Links</h4>
                    <div class="detail-row detail-row-social">
                        <span class="detail-label">GitHub:</span>
                        <span class="detail-value detail-value-social">
                            ${profile.github_url ? `
                                <a href="${escapeHtml(profile.github_url)}" target="_blank" class="social-link-large">
                                    <i class="fab fa-github"></i> <span class="social-url">${escapeHtml(profile.github_url)}</span>
                                </a>
                            ` : 'N/A'}
                        </span>
                    </div>
                    <div class="detail-row detail-row-social">
                        <span class="detail-label">LinkedIn:</span>
                        <span class="detail-value detail-value-social">
                            ${profile.linkedin_url ? `
                                <a href="${escapeHtml(profile.linkedin_url)}" target="_blank" class="social-link-large">
                                    <i class="fab fa-linkedin"></i> <span class="social-url">${escapeHtml(profile.linkedin_url)}</span>
                                </a>
                            ` : 'N/A'}
                        </span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h4><i class="fas fa-calendar"></i> Timestamps</h4>
                    <div class="detail-row">
                        <span class="detail-label">Registered At:</span>
                        <span class="detail-value">${formatDateTime(profile.registered_at) || 'N/A'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Created At:</span>
                        <span class="detail-value">${formatDateTime(profile.created_at) || 'N/A'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Updated At:</span>
                        <span class="detail-value">${formatDateTime(profile.updated_at) || 'N/A'}</span>
                    </div>
                </div>
                
                <div class="detail-section profile-cohort-grid-section">
                    <h4><i class="fas fa-th-large"></i> Track Progress</h4>
                    <table class="profile-cohort-grid" aria-label="Track progress by activity">
                        <thead>
                            <tr>
                                <th>COHORT 1</th>
                                <th>Track 1</th>
                                <th>Track 2</th>
                                <th>Track 3</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr><td class="grid-row-label">WEBINAR</td><td></td><td></td><td></td></tr>
                            <tr><td class="grid-row-label">MCQ</td><td></td><td></td><td></td></tr>
                            <tr><td class="grid-row-label">CODE LAB</td><td></td><td></td><td></td></tr>
                            <tr><td class="grid-row-label">PROJECT SUBMISSION</td><td></td><td></td><td></td></tr>
                            <tr><td class="grid-row-label">SKILL LAB</td><td></td><td></td><td></td></tr>
                        </tbody>
                    </table>
                </div>
                
                <div class="detail-section detail-section-logs">
                    <h4><i class="fas fa-history"></i> Activity Log</h4>
                    <div id="profileActivityLogList" class="activity-log-list">Loading...</div>
                </div>
            </div>
        `;
        
        console.log('Modal body populated, showing modal...');
        loadProfileLogs(profile.id);
        
        // Show modal
        const modal = document.getElementById('profileModal');
        if (modal) {
            console.log('Modal element found, setting display to flex');
            
            // Set fixed positioning styles
            modal.style.position = 'fixed';
            modal.style.top = '0';
            modal.style.left = '0';
            modal.style.width = '100vw';
            modal.style.height = '100vh';
            modal.style.zIndex = '10000';
            modal.style.display = 'flex';
            modal.style.alignItems = 'center';
            modal.style.justifyContent = 'center';
            modal.style.margin = '0';
            modal.style.padding = '0';
            
            // Prevent body scroll
            document.body.style.overflow = 'hidden';
            
            // Scroll to top of page to ensure modal is visible
            window.scrollTo({ top: 0, behavior: 'instant' });
            
            // Force display with setTimeout to ensure it shows
            setTimeout(() => {
                modal.style.display = 'flex';
                modal.style.position = 'fixed';
                modal.style.top = '0';
                modal.style.left = '0';
                console.log('Modal positioned and displayed');
            }, 10);
            
            // Click outside to close
            const modalContent = modal.querySelector('.modal-content');
            if (modalContent) {
                modalContent.onclick = function(e) {
                    e.stopPropagation();
                };
                // Ensure modal content is centered
                modalContent.style.margin = 'auto';
                modalContent.style.position = 'relative';
            }
            
            modal.onclick = function(e) {
                if (e.target === modal) {
                    closeProfileModal();
                }
            };
        } else {
            console.error('Modal element not found!');
            alert('Modal element not found. Please refresh the page.');
        }
    })
    .catch(error => {
        console.error('=== ERROR IN PROFILE FETCH ===');
        console.error('Error loading profile details:', error);
        console.error('Error type:', typeof error);
        console.error('Error name:', error.name);
        console.error('Error message:', error.message);
        if (error.stack) {
            console.error('Error stack:', error.stack);
        }
        console.error('Full error object:', error);
        alert('Failed to load profile details: ' + (error.message || 'Unknown error'));
    });
};

window.closeProfileModal = function() {
    const modal = document.getElementById('profileModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
};

// Load on page load
document.addEventListener('DOMContentLoaded', function() {
    loadFilterOptions();
    loadProfiles();
});

/**
 * Load filter options for dropdowns
 */
async function loadFilterOptions() {
    try {
        const token = localStorage.getItem('token');
        if (!token) return;
        
        const response = await fetch('/api/profiles/filters', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            filterOptions = await response.json();
            populateFilterDropdowns();
        }
    } catch (error) {
        console.error('Failed to load filter options:', error);
    }
}

/**
 * Populate filter dropdowns
 */
function populateFilterDropdowns() {
    const populateSelect = (id, options) => {
        const select = document.getElementById(id);
        if (!select) return;
        
        // Keep the first option (All/None)
        const firstOption = select.options[0];
        select.innerHTML = '';
        select.appendChild(firstOption);
        
        options.forEach(option => {
            const optionEl = document.createElement('option');
            optionEl.value = option;
            optionEl.textContent = option;
            select.appendChild(optionEl);
        });
    };
    
    populateSelect('filterOrganization', filterOptions.organizations || []);
    populateSelect('filterDomain', filterOptions.domains || []);
    populateSelect('filterCountry', filterOptions.countries || []);
    populateSelect('filterState', filterOptions.states || []);
    populateSelect('filterCity', filterOptions.cities || []);
    populateSelect('filterGender', filterOptions.genders || []);
    populateSelect('filterClassStream', filterOptions.class_streams || []);
    populateSelect('filterDesignation', filterOptions.designations || []);
    populateSelect('filterOccupation', filterOptions.occupations || []);
}

/**
 * Load profiles with current filters
 */
async function loadProfiles() {
    try {
        const token = localStorage.getItem('token');
        if (!token) {
            window.location.href = '/login';
            return;
        }
        
        const params = new URLSearchParams({
            page: currentPage,
            per_page: perPage,
            ...currentFilters
        });
        
        const response = await fetch(`/api/profiles?${params.toString()}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.status === 401) {
            localStorage.removeItem('token');
            window.location.href = '/login';
            return;
        }
        
        if (!response.ok) {
            throw new Error('Failed to load profiles');
        }
        
        const data = await response.json();
        renderProfiles(data.profiles);
        updatePagination(data.pagination);
        updateResultsCount(data.pagination);
        
    } catch (error) {
        console.error('Failed to load profiles:', error);
        const tbody = document.getElementById('profilesListBody');
        if (tbody) {
            tbody.innerHTML = 
                '<tr><td colspan="9" class="error-state">Failed to load profiles. Please try again.</td></tr>';
        }
    }
}

/**
 * Render profiles in list format
 */
function renderProfiles(profiles) {
    const tbody = document.getElementById('profilesListBody');
    
    if (profiles.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="empty-state">No profiles found matching your criteria.</td></tr>';
        return;
    }
    
    tbody.innerHTML = profiles.map(profile => `
        <tr class="profile-list-row">
            <td>
                <div class="profile-list-name">
                    <div class="profile-list-avatar">
                        <i class="fas fa-user"></i>
                    </div>
                    <div>
                        <div class="profile-list-name-text">${escapeHtml(profile.name || 'N/A')}</div>
                    </div>
                </div>
            </td>
            <td>
                <span class="profile-list-email">${escapeHtml(profile.email || 'N/A')}</span>
            </td>
            <td>
                <span class="profile-list-org">${escapeHtml(profile.organization_name || 'N/A')}</span>
            </td>
            <td>
                <span class="profile-list-bob">${profile.bob_match ? 'Yes' : 'No'}</span>
            </td>
            <td>
                <span class="profile-list-domain">${escapeHtml(profile.domain || 'N/A')}</span>
            </td>
            <td>
                <span class="profile-list-utm">${escapeHtml(profile.utm_medium || 'N/A')}</span>
            </td>
            <td>
                <span class="profile-list-location">${escapeHtml(formatLocation(profile))}</span>
            </td>
            <td>
                <div class="profile-list-social">
                    ${profile.github_url ? `
                        <a href="${escapeHtml(profile.github_url)}" target="_blank" class="social-link-list" title="GitHub">
                            <i class="fab fa-github"></i>
                        </a>
                    ` : '<span class="text-muted">-</span>'}
                    ${profile.linkedin_url ? `
                        <a href="${escapeHtml(profile.linkedin_url)}" target="_blank" class="social-link-list" title="LinkedIn">
                            <i class="fab fa-linkedin"></i>
                        </a>
                    ` : ''}
                    ${!profile.github_url && !profile.linkedin_url ? '<span class="text-muted">-</span>' : ''}
                </div>
            </td>
            <td>
                <div class="table-actions">
                    <button class="table-action-btn table-action-btn-view" onclick="viewProfileDetails('${profile.id}')" title="View Details">
                        <i class="fas fa-eye"></i>
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
}

/**
 * Format location string
 */
function formatLocation(profile) {
    const parts = [];
    if (profile.city) parts.push(profile.city);
    if (profile.state) parts.push(profile.state);
    if (profile.country) parts.push(profile.country);
    return parts.length > 0 ? parts.join(', ') : 'N/A';
}

/**
 * View profile details (async version - also available globally)
 */
async function viewProfileDetails(profileId) {
    console.log('viewProfileDetails called with ID:', profileId);
    
    try {
        // Get token
        const token = localStorage.getItem('token');
        if (!token) {
            alert('Please login to view profile details');
            window.location.href = '/login';
            return;
        }
        
        const url = `/api/profiles/${profileId}`;
        console.log('Fetching profile from:', url);
        
        // Make authenticated request
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.status === 401) {
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            window.location.href = '/login';
            return;
        }
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `Failed to load profile details (${response.status})`);
        }
        
        const data = await response.json();
        console.log('Profile data received:', data);
        
        const profile = data.profile;
        
        if (!profile) {
            throw new Error('Profile not found in response');
        }
        
        // Populate modal
        const modalNameEl = document.getElementById('modalProfileName');
        if (modalNameEl) {
            modalNameEl.textContent = profile.name || 'Profile Details';
        } else {
            console.error('Modal name element not found');
        }
        
        const modalBody = document.getElementById('profileModalBody');
        if (!modalBody) {
            console.error('Modal body element not found');
            alert('Modal not found. Please refresh the page.');
            return;
        }
        
        modalBody.innerHTML = `
            <div class="profile-detail-grid">
                <div class="detail-section">
                    <h4><i class="fas fa-info-circle"></i> Basic Information</h4>
                    <div class="detail-row">
                        <span class="detail-label">Name:</span>
                        <span class="detail-value">${escapeHtml(profile.name || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Email:</span>
                        <span class="detail-value">${escapeHtml(profile.email || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Mobile:</span>
                        <span class="detail-value">${escapeHtml(profile.mobile_number || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Date of Birth:</span>
                        <span class="detail-value">${formatDate(profile.date_of_birth) || 'N/A'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Gender:</span>
                        <span class="detail-value">${escapeHtml(profile.gender || 'N/A')}</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h4><i class="fas fa-briefcase"></i> Professional</h4>
                    <div class="detail-row">
                        <span class="detail-label">Organization:</span>
                        <span class="detail-value">${escapeHtml(profile.organization_name || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">BOB match:</span>
                        <span class="detail-value">${profile.bob_match ? 'Yes' : 'No'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Designation:</span>
                        <span class="detail-value">${escapeHtml(profile.designation || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Occupation:</span>
                        <span class="detail-value">${escapeHtml(profile.occupation || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Domain:</span>
                        <span class="detail-value">${escapeHtml(profile.domain || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">UTM medium:</span>
                        <span class="detail-value">${escapeHtml(profile.utm_medium || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Class Stream:</span>
                        <span class="detail-value">${escapeHtml(profile.class_stream || 'N/A')}</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h4><i class="fas fa-map-marker-alt"></i> Location</h4>
                    <div class="detail-row">
                        <span class="detail-label">Country:</span>
                        <span class="detail-value">${escapeHtml(profile.country || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">State:</span>
                        <span class="detail-value">${escapeHtml(profile.state || 'N/A')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">City:</span>
                        <span class="detail-value">${escapeHtml(profile.city || 'N/A')}</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h4><i class="fas fa-link"></i> Social Links</h4>
                    <div class="detail-row detail-row-social">
                        <span class="detail-label">GitHub:</span>
                        <span class="detail-value detail-value-social">
                            ${profile.github_url ? `
                                <a href="${escapeHtml(profile.github_url)}" target="_blank" class="social-link-large">
                                    <i class="fab fa-github"></i> <span class="social-url">${escapeHtml(profile.github_url)}</span>
                                </a>
                            ` : 'N/A'}
                        </span>
                    </div>
                    <div class="detail-row detail-row-social">
                        <span class="detail-label">LinkedIn:</span>
                        <span class="detail-value detail-value-social">
                            ${profile.linkedin_url ? `
                                <a href="${escapeHtml(profile.linkedin_url)}" target="_blank" class="social-link-large">
                                    <i class="fab fa-linkedin"></i> <span class="social-url">${escapeHtml(profile.linkedin_url)}</span>
                                </a>
                            ` : 'N/A'}
                        </span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h4><i class="fas fa-calendar"></i> Timestamps</h4>
                    <div class="detail-row">
                        <span class="detail-label">Registered At:</span>
                        <span class="detail-value">${formatDateTime(profile.registered_at) || 'N/A'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Created At:</span>
                        <span class="detail-value">${formatDateTime(profile.created_at) || 'N/A'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Updated At:</span>
                        <span class="detail-value">${formatDateTime(profile.updated_at) || 'N/A'}</span>
                    </div>
                </div>
                
                <div class="detail-section profile-cohort-grid-section">
                    <h4><i class="fas fa-th-large"></i> Track Progress</h4>
                    <table class="profile-cohort-grid" aria-label="Track progress by activity">
                        <thead>
                            <tr>
                                <th>COHORT 1</th>
                                <th>Track 1</th>
                                <th>Track 2</th>
                                <th>Track 3</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr><td class="grid-row-label">WEBINAR</td><td></td><td></td><td></td></tr>
                            <tr><td class="grid-row-label">MCQ</td><td></td><td></td><td></td></tr>
                            <tr><td class="grid-row-label">CODE LAB</td><td></td><td></td><td></td></tr>
                            <tr><td class="grid-row-label">PROJECT SUBMISSION</td><td></td><td></td><td></td></tr>
                            <tr><td class="grid-row-label">SKILL LAB</td><td></td><td></td><td></td></tr>
                        </tbody>
                    </table>
                </div>
                
                <div class="detail-section detail-section-logs">
                    <h4><i class="fas fa-history"></i> Activity Log</h4>
                    <div id="profileActivityLogList" class="activity-log-list">Loading...</div>
                </div>
            </div>
        `;
        
        loadProfileLogs(profile.id);
        
        // Show modal
        const modal = document.getElementById('profileModal');
        if (modal) {
            modal.style.display = 'flex';
            // Prevent body scroll when modal is open
            document.body.style.overflow = 'hidden';
            
            // Add click outside to close (only on backdrop, not content)
            const modalContent = modal.querySelector('.modal-content');
            if (modalContent) {
                modalContent.onclick = function(e) {
                    e.stopPropagation();
                };
            }
            
            const existingHandler = modal._clickHandler;
            if (existingHandler) {
                modal.removeEventListener('click', existingHandler);
            }
            
            modal._clickHandler = function(e) {
                if (e.target === modal) {
                    closeProfileModal();
                }
            };
            modal.addEventListener('click', modal._clickHandler);
            
            console.log('Modal displayed successfully');
        } else {
            console.error('Profile modal element not found');
            alert('Modal not found. Please refresh the page.');
        }
        
    } catch (error) {
        console.error('Error loading profile details:', error);
        alert('Failed to load profile details: ' + error.message);
    }
}

// Make function globally available immediately
window.viewProfileDetails = viewProfileDetails;

/**
 * Close profile modal
 */
function closeProfileModal() {
    const modal = document.getElementById('profileModal');
    if (modal) {
        modal.style.display = 'none';
        // Restore body scroll
        document.body.style.overflow = '';
    }
}

// Make functions globally available immediately
window.closeProfileModal = closeProfileModal;

/** Human-readable labels for filter keys (for Applied filters display) */
var FILTER_LABELS = {
    search: 'Search',
    organization: 'Organization',
    domain: 'Domain',
    country: 'Country',
    state: 'State',
    city: 'City',
    gender: 'Gender',
    class_stream: 'Class Stream',
    designation: 'Designation',
    occupation: 'Occupation',
    has_github: 'Has GitHub',
    has_linkedin: 'Has LinkedIn',
    bob_match: 'BOB match'
};

/**
 * Get display value for a filter (e.g. "Yes" for has_github true)
 */
function getFilterDisplayValue(key, value) {
    if (key === 'has_github' || key === 'has_linkedin' || key === 'bob_match') {
        if (value === 'true') return 'Yes';
        if (value === 'false') return 'No';
    }
    return value;
}

/**
 * Update the "Applied filters" section under the filter form
 */
function updateAppliedFiltersDisplay() {
    var wrap = document.getElementById('appliedFiltersWrap');
    var listEl = document.getElementById('appliedFiltersList');
    if (!wrap || !listEl) return;
    var applied = [];
    Object.keys(currentFilters).forEach(function (key) {
        var val = currentFilters[key];
        if (!val) return;
        var label = FILTER_LABELS[key] || key;
        var displayVal = getFilterDisplayValue(key, val);
        applied.push({ key: key, label: label, value: displayVal });
    });
    if (applied.length === 0) {
        wrap.style.display = 'none';
        listEl.innerHTML = '';
        return;
    }
    wrap.style.display = 'flex';
    listEl.innerHTML = applied.map(function (a) {
        return '<span class="applied-filter-chip">' + escapeHtml(a.label) + ': ' + escapeHtml(a.value) + '</span>';
    }).join('');
}

/**
 * Apply filters
 */
function applyFilters() {
    currentFilters = {
        search: document.getElementById('searchInput').value.trim(),
        organization: document.getElementById('filterOrganization').value,
        domain: document.getElementById('filterDomain').value,
        country: document.getElementById('filterCountry').value,
        state: document.getElementById('filterState').value,
        city: document.getElementById('filterCity').value,
        gender: document.getElementById('filterGender').value,
        class_stream: document.getElementById('filterClassStream').value,
        designation: document.getElementById('filterDesignation').value,
        occupation: document.getElementById('filterOccupation').value,
        has_github: document.getElementById('filterGithub').value,
        has_linkedin: document.getElementById('filterLinkedin').value,
        bob_match: document.getElementById('filterBob').value
    };
    
    // Remove empty filters
    Object.keys(currentFilters).forEach(function (key) {
        if (!currentFilters[key]) {
            delete currentFilters[key];
        }
    });
    
    currentPage = 1;
    updateAppliedFiltersDisplay();
    loadProfiles();
}

/**
 * Handle search input (with debounce)
 */
let searchTimeout;
function handleSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        applyFilters();
    }, 500);
}

/**
 * Clear all filters
 */
function clearFilters() {
    document.getElementById('searchInput').value = '';
    document.getElementById('filterOrganization').value = '';
    document.getElementById('filterDomain').value = '';
    document.getElementById('filterCountry').value = '';
    document.getElementById('filterState').value = '';
    document.getElementById('filterCity').value = '';
    document.getElementById('filterGender').value = '';
    document.getElementById('filterClassStream').value = '';
    document.getElementById('filterDesignation').value = '';
    document.getElementById('filterOccupation').value = '';
    document.getElementById('filterGithub').value = '';
    document.getElementById('filterLinkedin').value = '';
    document.getElementById('filterBob').value = '';
    
    currentFilters = {};
    currentPage = 1;
    updateAppliedFiltersDisplay();
    loadProfiles();
}

/**
 * Toggle filters section
 */
function toggleFilters() {
    const content = document.getElementById('filtersContent');
    const icon = document.getElementById('filterToggleIcon');
    
    if (content.style.display === 'none') {
        content.style.display = 'block';
        icon.classList.remove('fa-chevron-down');
        icon.classList.add('fa-chevron-up');
    } else {
        content.style.display = 'none';
        icon.classList.remove('fa-chevron-up');
        icon.classList.add('fa-chevron-down');
    }
}

/**
 * Change page
 */
function changePage(delta) {
    const newPage = currentPage + delta;
    if (newPage >= 1 && newPage <= totalPages) {
        currentPage = newPage;
        loadProfiles();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

/**
 * Change per page
 */
function changePerPage() {
    perPage = parseInt(document.getElementById('perPageSelect').value);
    currentPage = 1;
    loadProfiles();
}

/**
 * Update pagination UI
 */
function updatePagination(pagination) {
    totalPages = pagination.pages;
    const paginationEl = document.getElementById('pagination');
    const pageInfo = document.getElementById('pageInfo');
    const prevBtn = document.getElementById('prevPage');
    const nextBtn = document.getElementById('nextPage');
    
    if (totalPages <= 1) {
        paginationEl.style.display = 'none';
        return;
    }
    
    paginationEl.style.display = 'flex';
    pageInfo.textContent = `Page ${pagination.page} of ${pagination.pages}`;
    
    prevBtn.disabled = !pagination.has_prev;
    nextBtn.disabled = !pagination.has_next;
}

/**
 * Update results count
 */
function updateResultsCount(pagination) {
    const countEl = document.getElementById('resultsCount');
    const total = pagination.total || 0;
    const start = total === 0 ? 0 : (pagination.page - 1) * pagination.per_page + 1;
    const end = total === 0 ? 0 : Math.min(pagination.page * pagination.per_page, total);
    countEl.textContent = total === 0
        ? 'Showing 0 of 0 profiles'
        : `Showing ${start}-${end} of ${total.toLocaleString()} profiles`;
}

/**
 * Utility functions
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    if (!dateString) return null;
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
}

function formatDateTime(dateString) {
    if (!dateString) return null;
    const date = new Date(dateString);
    return date.toLocaleString('en-US', { 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}
