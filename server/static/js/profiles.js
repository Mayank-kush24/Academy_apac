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

/**
 * Generate HTML for a Skill Lab track cell in the Track Progress table.
 * Searches skilllab_submissions for a submission whose problem_statement contains the trackLabel.
 * Returns valid/not-valid markup with remark if applicable.
 */
function getSkillLabTrackCell(submissions, trackLabel) {
    if (!submissions || submissions.length === 0) return '';
    // Find a submission whose problem_statement contains the track label (case-insensitive)
    var match = submissions.find(function(s) {
        return s.problem_statement && s.problem_statement.toLowerCase().includes(trackLabel.toLowerCase());
    });
    if (!match) return '';
    // Not yet reviewed (no valid flag set and no remark)
    if (!match.valid && (!match.remark || !match.remark.trim())) {
        return '<span style="color:#999;font-size:0.8rem;">Pending</span>';
    }
    if (match.valid) {
        return '<span style="color:#22c55e;font-weight:600;"><i class="fas fa-check-circle"></i> Valid</span>';
    }
    // Not valid — show remark
    var html = '<span style="color:#ef4444;font-weight:600;"><i class="fas fa-times-circle"></i> Not Valid</span>';
    if (match.remark && match.remark.trim()) {
        html += '<br><span style="color:#666;font-size:0.75rem;" title="' + escapeHtml(match.remark) + '">' + escapeHtml(match.remark) + '</span>';
    }
    return html;
}

/**
 * Generate HTML for a Code Lab track cell in the Track Progress table.
 * Uses track_number (int) to group submissions per track.
 * Shows aggregated status across labs within that track.
 */
function getCodeLabTrackCell(submissions, trackLabel) {
    if (!submissions || submissions.length === 0) return '';
    var trackNum = trackLabel === 'Track 1' ? 1 : (trackLabel === 'Track 2' ? 2 : (trackLabel === 'Track 3' ? 3 : 0));
    if (!trackNum) return '';
    var matches = submissions.filter(function(s) { return s.track_number === trackNum; });
    if (matches.length === 0) return '';
    var validCount = matches.filter(function(s) { return s.valid; }).length;
    var invalidCount = matches.filter(function(s) { return !s.valid && s.remark && s.remark.trim(); }).length;
    var pendingCount = matches.length - validCount - invalidCount;
    var parts = [];
    if (validCount > 0) parts.push('<span style="color:#22c55e;font-weight:600;"><i class="fas fa-check-circle"></i> ' + validCount + ' Valid</span>');
    if (invalidCount > 0) parts.push('<span style="color:#ef4444;font-weight:600;"><i class="fas fa-times-circle"></i> ' + invalidCount + ' Not Valid</span>');
    if (pendingCount > 0) parts.push('<span style="color:#999;font-size:0.8rem;">' + pendingCount + ' Pending</span>');
    return parts.join('<br>');
}

/**
 * Final project submission for a track (one row per leader per track).
 * Shows team name plus verification stats (submitted / verified / pending review).
 */
function getProjectTrackCell(submissions, trackLabel) {
    if (!submissions || submissions.length === 0) return '';
    var trackNum = trackLabel === 'Track 1' ? 1 : (trackLabel === 'Track 2' ? 2 : (trackLabel === 'Track 3' ? 3 : 0));
    if (!trackNum) return '';
    var match = submissions.find(function(s) { return s.track_number === trackNum; });
    if (!match) {
        return '<span style="color:#d1d5db;font-size:0.75rem;">—</span>';
    }
    var team = (match.team_name && String(match.team_name).trim()) ? String(match.team_name).trim() : '';
    var teamLine = '';
    if (team) {
        var shortTeam = team.length > 36 ? team.slice(0, 33) + '…' : team;
        teamLine = '<div style="font-size:0.7rem;color:#4b5563;font-weight:600;margin-bottom:4px;line-height:1.25;" title="' + escapeHtml(team) + '">' + escapeHtml(shortTeam) + '</div>';
    }
    var statLine = '<div style="font-size:0.68rem;color:#6b7280;margin-bottom:2px;">1 submission</div>';
    var statusBlock = '';
    if (!match.valid && (!match.remark || !match.remark.trim())) {
        statusBlock = '<span style="color:#ca8a04;font-weight:600;font-size:0.75rem;"><i class="fas fa-hourglass-half"></i> Pending review</span>';
    } else if (match.valid) {
        statusBlock = '<span style="color:#16a34a;font-weight:600;font-size:0.75rem;"><i class="fas fa-check-circle"></i> Verified</span>';
    } else {
        statusBlock = '<span style="color:#dc2626;font-weight:600;font-size:0.75rem;"><i class="fas fa-times-circle"></i> Not valid</span>';
        if (match.remark && match.remark.trim()) {
            statusBlock += '<br><span style="color:#6b7280;font-size:0.68rem;" title="' + escapeHtml(match.remark) + '">' + escapeHtml(match.remark.length > 48 ? match.remark.slice(0, 45) + '…' : match.remark) + '</span>';
        }
    }
    return teamLine + statLine + statusBlock;
}

/**
 * Webinar is auto-valid for a track if any Code Lab submission exists for that track.
 */
function getWebinarTrackCell(codelabSubmissions, trackLabel) {
    if (!codelabSubmissions || codelabSubmissions.length === 0) return '';
    var trackNum = trackLabel === 'Track 1' ? 1 : (trackLabel === 'Track 2' ? 2 : (trackLabel === 'Track 3' ? 3 : 0));
    if (!trackNum) return '';
    var hasSubmission = codelabSubmissions.some(function(s) { return s.track_number === trackNum; });
    if (!hasSubmission) return '';
    return '<span style="color:#22c55e;font-weight:600;"><i class="fas fa-check-circle"></i> Valid</span>';
}

function getOptionalMcqTrackCell(scores, trackLabel) {
    if (!scores || scores.length === 0) return '';
    var trackNum = trackLabel === 'Track 1' ? 1 : (trackLabel === 'Track 2' ? 2 : (trackLabel === 'Track 3' ? 3 : 0));
    if (!trackNum) return '';
    var item = scores.find(function(s) { return s.track_number === trackNum; });
    if (!item || item.score_display == null) return '';
    var scoreDisplay = String(item.score_display);
    var score = typeof item.score === 'number' ? item.score : parseInt(scoreDisplay.split('/')[0], 10);
    var isPass = !isNaN(score) && score >= 6;
    var label = isPass ? 'Verified' : 'Fail';
    var color = isPass ? '#16a34a' : '#dc2626';
    return '<span style="color:' + color + ';font-weight:600;">' + escapeHtml(label) + '</span>';
}

/**
 * Generate HTML for a Main MCQ (MCQ Verification) track cell.
 * Shows Verified when score >= 6, Fail when submitted but < 6.
 */
function getMainMcqTrackCell(scores, trackLabel) {
    if (!scores || scores.length === 0) return '';
    var trackNum = trackLabel === 'Track 1' ? 1 : (trackLabel === 'Track 2' ? 2 : (trackLabel === 'Track 3' ? 3 : 0));
    if (!trackNum) return '';
    var item = scores.find(function(s) { return s.track_number === trackNum; });
    if (!item) return '';
    var score = typeof item.score === 'number' ? item.score : parseInt(String(item.score_display || '').split('/')[0], 10);
    var isPass = !isNaN(score) && score >= 6;
    var label = isPass ? 'Verified' : 'Fail';
    var color = isPass ? '#16a34a' : '#dc2626';
    return '<span style="color:' + color + ';font-weight:600;"><i class="fas fa-check-circle"></i> ' + escapeHtml(label) + '</span>';
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
            const time = log.created_at || '';
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
        const skillboost_profiles = data.skillboost_profiles || [];
        const skilllab_submissions = data.skilllab_submissions || [];
        const codelab_submissions = data.codelab_submissions || [];
        const project_submissions = data.project_submissions || [];
        const optional_mcq_scores = data.optional_mcq_scores || [];
        const main_mcq_scores = data.main_mcq_scores || [];
        
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
                
                <div class="detail-section skillboost-section-wrap">
                    <h4><i class="fas fa-graduation-cap"></i> Skill Lab / Skillboost profiles</h4>
                    ${skillboost_profiles.length === 0 ? '<p class="detail-value text-muted">No Skill Lab profiles for this user.</p>' : (function(){
                        var v = 0, p = 0, f = 0;
                        skillboost_profiles.forEach(function(sp) { if (sp.valid) v++; else if (sp.remarks) f++; else p++; });
                        var summary = '<div class="skillboost-summary-bar"><span class="skillboost-summary-label">Verification status</span><span class="skillboost-summary-value">' + v + ' verified, ' + p + ' pending, ' + f + ' failed</span></div>';
                        return '<div class="skillboost-section-card">' + summary + skillboost_profiles.map(function(sp) {
                            var status = sp.valid ? 'Verified' : (sp.remarks ? 'Failed' : 'Pending');
                            var statusClass = sp.valid ? 'skillboost-verified' : (sp.remarks ? 'skillboost-failed' : 'skillboost-pending');
                            var linkVal = sp.google_cloud_skills_boost_profile_link || '';
                            var linkEsc = escapeHtml(linkVal);
                            var remarks = sp.remarks ? escapeHtml(sp.remarks) : '';
                            var linkHtml = linkVal ? '<a href="' + linkEsc + '" target="_blank" class="skillboost-profile-link">' + linkEsc + '</a>' : '<span class="text-muted">No profile link provided</span>';
                            var allocatedLink = (sp.link_display_order != null) ? ('Link ' + sp.link_display_order + (sp.link_url ? ' – ' + escapeHtml((sp.link_url || '').slice(0, 60)) + ((sp.link_url || '').length > 60 ? '…' : '') : '')) : '<span class="text-muted">—</span>';
                            var emailSent = sp.email_sent_at ? formatDateTime(sp.email_sent_at) : '<span class="text-muted">No</span>';
                            var allocatedAt = sp.allocated_at ? formatDateTime(sp.allocated_at) : '<span class="text-muted">—</span>';
                            return '<div class="skillboost-profile-card">' +
                                '<div class="skillboost-profile-header">' + linkHtml + ' <span class="skillboost-status-badge ' + statusClass + '">' + escapeHtml(status) + '</span>' + (remarks ? ' <span class="skillboost-remarks text-muted">' + remarks + '</span>' : '') + '</div>' +
                                '<div class="skillboost-detail-rows">' +
                                '<div class="detail-row"><span class="detail-label">Allocated credit link</span><span class="detail-value">' + allocatedLink + '</span></div>' +
                                '<div class="detail-row"><span class="detail-label">Email sent</span><span class="detail-value">' + emailSent + '</span></div>' +
                                '<div class="detail-row"><span class="detail-label">Allocated at</span><span class="detail-value">' + allocatedAt + '</span></div>' +
                                '</div></div>';
                        }).join('') + '</div>';
                    })()}
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
                            <tr><td class="grid-row-label">WEBINAR</td><td>${getWebinarTrackCell(codelab_submissions, 'Track 1')}</td><td>${getWebinarTrackCell(codelab_submissions, 'Track 2')}</td><td>${getWebinarTrackCell(codelab_submissions, 'Track 3')}</td></tr>
                            <tr><td class="grid-row-label">MCQ</td><td>${getMainMcqTrackCell(main_mcq_scores, 'Track 1')}</td><td>${getMainMcqTrackCell(main_mcq_scores, 'Track 2')}</td><td>${getMainMcqTrackCell(main_mcq_scores, 'Track 3')}</td></tr>
                            <tr><td class="grid-row-label">Optional MCQ</td><td>${getOptionalMcqTrackCell(optional_mcq_scores, 'Track 1')}</td><td>${getOptionalMcqTrackCell(optional_mcq_scores, 'Track 2')}</td><td>${getOptionalMcqTrackCell(optional_mcq_scores, 'Track 3')}</td></tr>
                            <tr><td class="grid-row-label">CODE LAB</td><td>${getCodeLabTrackCell(codelab_submissions, 'Track 1')}</td><td>${getCodeLabTrackCell(codelab_submissions, 'Track 2')}</td><td>${getCodeLabTrackCell(codelab_submissions, 'Track 3')}</td></tr>
                            <tr><td class="grid-row-label">PROJECT SUBMISSION</td><td>${getProjectTrackCell(project_submissions, 'Track 1')}</td><td>${getProjectTrackCell(project_submissions, 'Track 2')}</td><td>${getProjectTrackCell(project_submissions, 'Track 3')}</td></tr>
                            <tr><td class="grid-row-label">SKILL LAB</td><td>${getSkillLabTrackCell(skilllab_submissions, 'Track 1')}</td><td>${getSkillLabTrackCell(skilllab_submissions, 'Track 2')}</td><td>${getSkillLabTrackCell(skilllab_submissions, 'Track 3')}</td></tr>
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
    var MULTI_SEP = '|';
    var searchableConfigs = [
        { filter: 'organization', items: filterOptions.organizations || [] },
        { filter: 'domain', items: filterOptions.domains || [] },
        { filter: 'country', items: filterOptions.countries || [] },
        { filter: 'state', items: filterOptions.states || [] },
        { filter: 'city', items: filterOptions.cities || [] },
        { filter: 'gender', items: filterOptions.genders || [] },
        { filter: 'class_stream', items: filterOptions.class_streams || [] },
        { filter: 'designation', items: filterOptions.designations || [] },
        { filter: 'occupation', items: filterOptions.occupations || [] }
    ];
    searchableConfigs.forEach(function (cfg) {
        var wrap = document.querySelector('.searchable-select[data-filter="' + cfg.filter + '"]');
        if (!wrap) return;
        var allLabel = wrap.dataset.allLabel || 'All';
        var list = wrap.querySelector('.searchable-select-list');
        if (!list) return;
        list.innerHTML = '';
        (cfg.items || []).forEach(function (item) {
            var li = document.createElement('li');
            li.setAttribute('data-value', item);
            li.textContent = item;
            list.appendChild(li);
        });
    });
    initProfileSearchableSelects();
}

function initProfileSearchableSelects() {
    var MULTI_SEP = '|';
    var container = document.getElementById('profilesPageContainer');
    if (!container) return;
    container.querySelectorAll('.searchable-select').forEach(function (wrap) {
        if (wrap._ssInit) return;
        wrap._ssInit = true;
        var trigger = wrap.querySelector('.searchable-select-trigger');
        var valueSpan = trigger && trigger.querySelector('.searchable-select-value');
        var dropdown = wrap.querySelector('.searchable-select-dropdown');
        var searchInp = dropdown && dropdown.querySelector('.searchable-select-search');
        var list = dropdown && dropdown.querySelector('.searchable-select-list');
        var hiddenInput = wrap.querySelector('input[type="hidden"]');
        var clearBtn = dropdown && dropdown.querySelector('.searchable-select-clear');
        var allLabel = wrap.dataset.allLabel || 'All';
        if (!trigger || !dropdown || !list || !hiddenInput) return;

        function getSelectedValues() {
            var out = [];
            list.querySelectorAll('li.selected').forEach(function (l) {
                var v = l.getAttribute('data-value') || '';
                if (v) out.push(v);
            });
            return out;
        }
        function syncFromInput() {
            var raw = (hiddenInput.value || '').trim();
            var vals = raw ? raw.split(MULTI_SEP).map(function (s) { return s.trim(); }).filter(Boolean) : [];
            list.querySelectorAll('li').forEach(function (l) {
                var v = l.getAttribute('data-value') || '';
                l.classList.toggle('selected', vals.indexOf(v) !== -1);
            });
            updateTriggerText();
        }
        function updateTriggerText() {
            var vals = getSelectedValues();
            if (vals.length === 0) { if (valueSpan) valueSpan.textContent = allLabel; return; }
            if (valueSpan) valueSpan.textContent = vals.length === 1 ? vals[0] : (vals.length + ' selected');
        }
        function open() {
            wrap.classList.add('open');
            syncFromInput();
            if (searchInp) { searchInp.value = ''; list.querySelectorAll('li').forEach(function (li) { li.classList.remove('hidden'); }); searchInp.focus(); }
        }
        function close() { wrap.classList.remove('open'); }
        trigger.addEventListener('click', function (e) {
            e.stopPropagation();
            var isOpen = wrap.classList.contains('open');
            container.querySelectorAll('.searchable-select.open').forEach(function (o) {
                if (o !== wrap) o.classList.remove('open');
            });
            if (isOpen) close(); else open();
        });
        if (searchInp) {
            searchInp.addEventListener('keyup', function () {
                var q = (searchInp.value || '').toLowerCase().trim();
                list.querySelectorAll('li').forEach(function (li) {
                    li.classList.toggle('hidden', q && (li.textContent || '').toLowerCase().indexOf(q) === -1);
                });
            });
            searchInp.addEventListener('click', function (e) { e.stopPropagation(); });
        }
        list.addEventListener('click', function (e) {
            var li = e.target.closest('li');
            if (!li) return;
            e.stopPropagation();
            li.classList.toggle('selected');
            var selected = getSelectedValues();
            hiddenInput.value = selected.join(MULTI_SEP);
            updateTriggerText();
        });
        if (clearBtn) clearBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            hiddenInput.value = '';
            list.querySelectorAll('li').forEach(function (l) { l.classList.remove('selected'); });
            updateTriggerText();
        });
        dropdown.addEventListener('click', function (e) { e.stopPropagation(); });
    });
    document.addEventListener('mousedown', function (e) {
        if (e.target && !e.target.closest('.searchable-select')) {
            (container || document).querySelectorAll('.searchable-select.open').forEach(function (w) {
                w.classList.remove('open');
            });
        }
    });
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
        
        const params = new URLSearchParams();
        params.set('page', currentPage);
        params.set('per_page', perPage);
        Object.keys(currentFilters).forEach(function (key) {
            var val = currentFilters[key];
            if (val == null || val === '') return;
            if (Array.isArray(val)) {
                val.forEach(function (v) { if (v) params.append(key, v); });
            } else {
                params.set(key, val);
            }
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
                '<tr><td colspan="10" class="error-state">Failed to load profiles. Please try again.</td></tr>';
        }
    }
}

/**
 * Render profiles in list format
 */
function renderProfiles(profiles) {
    const tbody = document.getElementById('profilesListBody');
    
    if (profiles.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="empty-state">No profiles found matching your criteria.</td></tr>';
        return;
    }
    
    tbody.innerHTML = profiles.map(profile => {
        const v = profile.skillboost_verification || { total: 0, verified: 0, pending: 0, failed: 0 };
        let skillLabHtml = '—';
        if (v.total > 0) {
            if (v.verified === v.total) skillLabHtml = '<span class="skillboost-badge verified" title="All verified">' + v.verified + '/' + v.total + ' verified</span>';
            else if (v.failed === v.total) skillLabHtml = '<span class="skillboost-badge failed" title="All failed">' + v.total + ' failed</span>';
            else skillLabHtml = '<span class="skillboost-badge partial" title="Verified: ' + v.verified + ', Pending: ' + v.pending + ', Failed: ' + v.failed + '">' + v.verified + '/' + v.total + ' verified</span>';
        }
        return `
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
                <span class="profile-list-skilllab">${skillLabHtml}</span>
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
    `;
    }).join('');
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
        const skillboost_profiles = data.skillboost_profiles || [];
        const skilllab_submissions = data.skilllab_submissions || [];
        const codelab_submissions = data.codelab_submissions || [];
        const project_submissions = data.project_submissions || [];
        const optional_mcq_scores = data.optional_mcq_scores || [];
        
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
                
                <div class="detail-section skillboost-section-wrap">
                    <h4><i class="fas fa-graduation-cap"></i> Skill Lab / Skillboost profiles</h4>
                    ${skillboost_profiles.length === 0 ? '<p class="detail-value text-muted">No Skill Lab profiles for this user.</p>' : (function(){
                        var v = 0, p = 0, f = 0;
                        skillboost_profiles.forEach(function(sp) { if (sp.valid) v++; else if (sp.remarks) f++; else p++; });
                        var summary = '<div class="skillboost-summary-bar"><span class="skillboost-summary-label">Verification status</span><span class="skillboost-summary-value">' + v + ' verified, ' + p + ' pending, ' + f + ' failed</span></div>';
                        return '<div class="skillboost-section-card">' + summary + skillboost_profiles.map(function(sp) {
                            var status = sp.valid ? 'Verified' : (sp.remarks ? 'Failed' : 'Pending');
                            var statusClass = sp.valid ? 'skillboost-verified' : (sp.remarks ? 'skillboost-failed' : 'skillboost-pending');
                            var linkVal = sp.google_cloud_skills_boost_profile_link || '';
                            var linkEsc = escapeHtml(linkVal);
                            var remarks = sp.remarks ? escapeHtml(sp.remarks) : '';
                            var linkHtml = linkVal ? '<a href="' + linkEsc + '" target="_blank" class="skillboost-profile-link">' + linkEsc + '</a>' : '<span class="text-muted">No profile link provided</span>';
                            var allocatedLink = (sp.link_display_order != null) ? ('Link ' + sp.link_display_order + (sp.link_url ? ' – ' + escapeHtml((sp.link_url || '').slice(0, 60)) + ((sp.link_url || '').length > 60 ? '…' : '') : '')) : '<span class="text-muted">—</span>';
                            var emailSent = sp.email_sent_at ? formatDateTime(sp.email_sent_at) : '<span class="text-muted">No</span>';
                            var allocatedAt = sp.allocated_at ? formatDateTime(sp.allocated_at) : '<span class="text-muted">—</span>';
                            return '<div class="skillboost-profile-card">' +
                                '<div class="skillboost-profile-header">' + linkHtml + ' <span class="skillboost-status-badge ' + statusClass + '">' + escapeHtml(status) + '</span>' + (remarks ? ' <span class="skillboost-remarks text-muted">' + remarks + '</span>' : '') + '</div>' +
                                '<div class="skillboost-detail-rows">' +
                                '<div class="detail-row"><span class="detail-label">Allocated credit link</span><span class="detail-value">' + allocatedLink + '</span></div>' +
                                '<div class="detail-row"><span class="detail-label">Email sent</span><span class="detail-value">' + emailSent + '</span></div>' +
                                '<div class="detail-row"><span class="detail-label">Allocated at</span><span class="detail-value">' + allocatedAt + '</span></div>' +
                                '</div></div>';
                        }).join('') + '</div>';
                    })()}
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
                            <tr><td class="grid-row-label">WEBINAR</td><td>${getWebinarTrackCell(codelab_submissions, 'Track 1')}</td><td>${getWebinarTrackCell(codelab_submissions, 'Track 2')}</td><td>${getWebinarTrackCell(codelab_submissions, 'Track 3')}</td></tr>
                            <tr><td class="grid-row-label">MCQ</td><td>${getMainMcqTrackCell(main_mcq_scores, 'Track 1')}</td><td>${getMainMcqTrackCell(main_mcq_scores, 'Track 2')}</td><td>${getMainMcqTrackCell(main_mcq_scores, 'Track 3')}</td></tr>
                            <tr><td class="grid-row-label">Optional MCQ</td><td>${getOptionalMcqTrackCell(optional_mcq_scores, 'Track 1')}</td><td>${getOptionalMcqTrackCell(optional_mcq_scores, 'Track 2')}</td><td>${getOptionalMcqTrackCell(optional_mcq_scores, 'Track 3')}</td></tr>
                            <tr><td class="grid-row-label">CODE LAB</td><td>${getCodeLabTrackCell(codelab_submissions, 'Track 1')}</td><td>${getCodeLabTrackCell(codelab_submissions, 'Track 2')}</td><td>${getCodeLabTrackCell(codelab_submissions, 'Track 3')}</td></tr>
                            <tr><td class="grid-row-label">PROJECT SUBMISSION</td><td>${getProjectTrackCell(project_submissions, 'Track 1')}</td><td>${getProjectTrackCell(project_submissions, 'Track 2')}</td><td>${getProjectTrackCell(project_submissions, 'Track 3')}</td></tr>
                            <tr><td class="grid-row-label">SKILL LAB</td><td>${getSkillLabTrackCell(skilllab_submissions, 'Track 1')}</td><td>${getSkillLabTrackCell(skilllab_submissions, 'Track 2')}</td><td>${getSkillLabTrackCell(skilllab_submissions, 'Track 3')}</td></tr>
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
        if (val == null || val === '' || (Array.isArray(val) && val.length === 0)) return;
        var label = FILTER_LABELS[key] || key;
        var displayVal = Array.isArray(val) ? val.map(function (v) { return getFilterDisplayValue(key, v); }).join(', ') : getFilterDisplayValue(key, val);
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
 * Get selected values from a searchable-select hidden input (pipe-separated) as array
 */
function getMultiFilterValues(id) {
    var raw = (document.getElementById(id) && document.getElementById(id).value) || '';
    if (!raw.trim()) return [];
    return raw.split('|').map(function (s) { return s.trim(); }).filter(Boolean);
}

/**
 * Apply filters
 */
function applyFilters() {
    currentFilters = {
        search: document.getElementById('searchInput').value.trim(),
        organization: getMultiFilterValues('filterOrganization'),
        domain: getMultiFilterValues('filterDomain'),
        country: getMultiFilterValues('filterCountry'),
        state: getMultiFilterValues('filterState'),
        city: getMultiFilterValues('filterCity'),
        gender: getMultiFilterValues('filterGender'),
        class_stream: getMultiFilterValues('filterClassStream'),
        designation: getMultiFilterValues('filterDesignation'),
        occupation: getMultiFilterValues('filterOccupation'),
        has_github: document.getElementById('filterGithub').value,
        has_linkedin: document.getElementById('filterLinkedin').value,
        bob_match: document.getElementById('filterBob').value
    };
    
    // Remove empty filters
    Object.keys(currentFilters).forEach(function (key) {
        var v = currentFilters[key];
        if (v == null || v === '' || (Array.isArray(v) && v.length === 0)) {
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
 * Clear all filters (reset all searchable-selects and single selects)
 */
function clearFilters() {
    document.getElementById('searchInput').value = '';
    var container = document.getElementById('profilesPageContainer');
    if (container) {
        container.querySelectorAll('.searchable-select').forEach(function (wrap) {
            var hiddenInput = wrap.querySelector('input[type="hidden"]');
            if (hiddenInput) hiddenInput.value = '';
            var valueSpan = wrap.querySelector('.searchable-select-value');
            if (valueSpan) valueSpan.textContent = wrap.dataset.allLabel || 'All';
            var list = wrap.querySelector('.searchable-select-list');
            if (list) list.querySelectorAll('li').forEach(function (li) { li.classList.remove('selected', 'hidden'); });
            wrap.classList.remove('open');
        });
    }
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
    if (!content || !icon) return;

    const isCollapsed = content.classList.contains('filters-content--collapsed');
    if (isCollapsed) {
        content.classList.remove('filters-content--collapsed');
        content.setAttribute('aria-expanded', 'true');
        icon.classList.remove('fa-chevron-down');
        icon.classList.add('fa-chevron-up');
    } else {
        content.classList.add('filters-content--collapsed');
        content.setAttribute('aria-expanded', 'false');
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
