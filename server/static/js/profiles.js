/**
 * User Profiles JavaScript
 */

let currentPage = 1;
let perPage = 20;
let totalPages = 1;
let filterOptions = {};
let currentFilters = {};

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
        const response = await authenticatedFetch('/api/profiles/filters');
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
        const params = new URLSearchParams({
            page: currentPage,
            per_page: perPage,
            ...currentFilters
        });
        
        const response = await authenticatedFetch(`/api/profiles?${params.toString()}`);
        if (!response.ok) {
            throw new Error('Failed to load profiles');
        }
        
        const data = await response.json();
        renderProfiles(data.profiles);
        updatePagination(data.pagination);
        updateResultsCount(data.pagination);
        
    } catch (error) {
        console.error('Failed to load profiles:', error);
        document.getElementById('profilesListBody').innerHTML = 
            '<tr><td colspan="8" class="error-state">Failed to load profiles. Please try again.</td></tr>';
    }
}

/**
 * Render profiles in list format
 */
function renderProfiles(profiles) {
    const tbody = document.getElementById('profilesListBody');
    
    if (profiles.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No profiles found matching your criteria.</td></tr>';
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
                <span class="profile-list-domain">${escapeHtml(profile.domain || 'N/A')}</span>
            </td>
            <td>
                <span class="profile-list-location">${escapeHtml(formatLocation(profile))}</span>
            </td>
            <td>
                <span class="profile-list-designation">${escapeHtml(profile.designation || 'N/A')}</span>
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
 * View profile details
 */
async function viewProfileDetails(profileId) {
    try {
        const response = await authenticatedFetch(`/api/profiles/${profileId}`);
        if (!response.ok) {
            throw new Error('Failed to load profile details');
        }
        
        const data = await response.json();
        const profile = data.profile;
        
        // Populate modal
        document.getElementById('modalProfileName').textContent = profile.name || 'Profile Details';
        
        const modalBody = document.getElementById('profileModalBody');
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
                    <div class="detail-row">
                        <span class="detail-label">GitHub:</span>
                        <span class="detail-value">
                            ${profile.github_url ? `
                                <a href="${escapeHtml(profile.github_url)}" target="_blank" class="social-link-large">
                                    <i class="fab fa-github"></i> ${escapeHtml(profile.github_url)}
                                </a>
                            ` : 'N/A'}
                        </span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">LinkedIn:</span>
                        <span class="detail-value">
                            ${profile.linkedin_url ? `
                                <a href="${escapeHtml(profile.linkedin_url)}" target="_blank" class="social-link-large">
                                    <i class="fab fa-linkedin"></i> ${escapeHtml(profile.linkedin_url)}
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
            </div>
        `;
        
        // Show modal
        document.getElementById('profileModal').style.display = 'flex';
        
    } catch (error) {
        alert('Failed to load profile details: ' + error.message);
    }
}

/**
 * Close profile modal
 */
function closeProfileModal() {
    document.getElementById('profileModal').style.display = 'none';
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
        has_linkedin: document.getElementById('filterLinkedin').value
    };
    
    // Remove empty filters
    Object.keys(currentFilters).forEach(key => {
        if (!currentFilters[key]) {
            delete currentFilters[key];
        }
    });
    
    currentPage = 1;
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
    
    currentFilters = {};
    currentPage = 1;
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
    const start = (pagination.page - 1) * pagination.per_page + 1;
    const end = Math.min(pagination.page * pagination.per_page, pagination.total);
    countEl.textContent = `Showing ${start}-${end} of ${pagination.total} profiles`;
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
