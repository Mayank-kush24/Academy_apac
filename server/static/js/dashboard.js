/**
 * Dashboard JavaScript
 */

let charts = {};
let isLoading = false; // Prevent multiple simultaneous loads
let currentPeriod = '30d'; // Default period

// Load dashboard data on page load
document.addEventListener('DOMContentLoaded', function() {
    // Only load if we're on the dashboard page
    if (window.location.pathname === '/dashboard') {
        initializeDashboard();
        loadDashboardData();
    }
});

/**
 * Initialize dashboard interactions
 */
function initializeDashboard() {
    // Time period filter pills
    const periodPills = document.querySelectorAll('.pill[data-period]');
    periodPills.forEach(pill => {
        pill.addEventListener('click', function() {
            const period = this.getAttribute('data-period');
            setPeriod(period);
        });
    });
    
    // Keyboard shortcut for command palette (⌘K or Ctrl+K)
    document.addEventListener('keydown', function(e) {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            openCommandPalette();
        }
    });
}

/**
 * Set time period and reload data
 */
function setPeriod(period) {
    currentPeriod = period;
    
    // Update active pill
    document.querySelectorAll('.pill[data-period]').forEach(pill => {
        pill.classList.remove('active');
        if (pill.getAttribute('data-period') === period) {
            pill.classList.add('active');
        }
    });
    
    // Reload dashboard data with new period
    loadDashboardData();
}

/**
 * Load dashboard summary and charts
 */
async function loadDashboardData() {
    // Prevent multiple simultaneous loads
    if (isLoading) {
        return;
    }
    
    isLoading = true;
    
    // Show loading state
    const loadingIndicator = document.querySelector('.command-bar');
    if (loadingIndicator) {
        loadingIndicator.style.opacity = '0.7';
    }
    
    try {
        // Load summary with period parameter
        const summaryUrl = `/api/dashboard/summary?period=${currentPeriod}`;
        const summaryResponse = await authenticatedFetch(summaryUrl);
        let summary = null;
        if (summaryResponse.ok) {
            summary = await summaryResponse.json();
            updateKPICards(summary);
        } else {
            // If error, show empty state
            summary = {
                total_users: 0,
                unique_organizations: 0,
                top_domain: 'N/A',
                top_city: 'N/A'
            };
            updateKPICards(summary);
        }
        
        // Load charts with period parameter
        const chartsUrl = `/api/dashboard/charts?period=${currentPeriod}`;
        const chartsResponse = await authenticatedFetch(chartsUrl);
        if (chartsResponse.ok) {
            const chartsData = await chartsResponse.json();
            renderCharts(chartsData, summary);
        } else {
            // If error, show empty charts
            renderCharts({
                registration_trends: [],
                gender_distribution: [],
                top_domains: [],
                top_cities: [],
                top_organizations: []
            }, summary);
        }
    } catch (error) {
        console.error('Failed to load dashboard data:', error);
        // Show empty state instead of error
        updateKPICards({
            total_users: 0,
            unique_organizations: 0,
            top_domain: 'N/A',
            top_city: 'N/A'
        });
        renderCharts({
            registration_trends: [],
            gender_distribution: [],
            top_domains: [],
            top_cities: [],
            top_organizations: []
        });
    } finally {
        isLoading = false;
        // Remove loading state
        const loadingIndicator = document.querySelector('.command-bar');
        if (loadingIndicator) {
            loadingIndicator.style.opacity = '1';
        }
    }
}

/**
 * Update KPI cards - Enterprise style (metric strips)
 */
function updateKPICards(summary) {
    // Update metric values
    const totalUsersEl = document.getElementById('totalUsers');
    const uniqueOrgsEl = document.getElementById('uniqueOrgs');
    const topDomainEl = document.getElementById('topDomain');
    const topCityEl = document.getElementById('topCity');
    
    if (totalUsersEl) {
        totalUsersEl.textContent = summary.total_users || 0;
    }
    
    if (uniqueOrgsEl) {
        uniqueOrgsEl.textContent = summary.unique_organizations || 0;
    }
    
    if (topDomainEl) {
        const domain = summary.top_domain || 'N/A';
        // Don't truncate - let CSS handle overflow with word-wrap
        topDomainEl.textContent = domain;
        topDomainEl.title = domain; // Tooltip for full text
    }
    
    if (topCityEl) {
        topCityEl.textContent = summary.top_city || 'N/A';
    }
    
    // Update change indicators (placeholder - would come from API)
    const totalUsersChangeEl = document.getElementById('totalUsersChange');
    const uniqueOrgsChangeEl = document.getElementById('uniqueOrgsChange');
    
    if (totalUsersChangeEl) {
        totalUsersChangeEl.textContent = '+12% WoW';
        totalUsersChangeEl.classList.add('positive');
    }
    
    if (uniqueOrgsChangeEl) {
        uniqueOrgsChangeEl.textContent = '+5% WoW';
        uniqueOrgsChangeEl.classList.add('positive');
    }
}

/**
 * Render charts - Enterprise style
 */
function renderCharts(data, summary = null) {
    // Registration Trends (Line Chart) - Full width
    if (data.registration_trends && data.registration_trends.length > 0) {
        renderLineChart('registrationTrendsChart', 'Registration Trends', data.registration_trends);
    } else {
        showEmptyChart('registrationTrendsChart', 'No registration trend data available');
    }
    
    // Gender Distribution (Donut Chart) - Insights panel
    if (data.gender_distribution && data.gender_distribution.length > 0) {
        renderDonutChart('genderChart', 'Gender Distribution', data.gender_distribution);
    } else {
        showEmptyChart('genderChart', 'No gender data available');
    }
    
    // Top Domains (Bar Chart)
    if (data.top_domains && data.top_domains.length > 0) {
        renderBarChart('domainsChart', 'Top Domains', data.top_domains);
    } else {
        showEmptyChart('domainsChart', 'No domain data available');
    }
    
    // Top Cities (Bar Chart)
    if (data.top_cities && data.top_cities.length > 0) {
        renderBarChart('citiesChart', 'Top Cities', data.top_cities);
    } else {
        showEmptyChart('citiesChart', 'No city data available');
    }
    
    // Top Organizations (Bar Chart)
    if (data.top_organizations && data.top_organizations.length > 0) {
        renderBarChart('organizationsChart', 'Top Organizations', data.top_organizations);
    } else {
        showEmptyChart('organizationsChart', 'No organization data available');
    }
    
    // Generate insights (pass both chart data and summary)
    generateInsights(data, summary);
}

/**
 * Generate comprehensive natural language insights from data
 * Designed as a data intelligence module, not a chatbot
 */
function generateInsights(data, summary) {
    const insightsList = document.getElementById('insightsList');
    if (!insightsList) return;
    
    const insights = [];
    
    // 1. Registration Trend Analysis
    if (data.registration_trends && data.registration_trends.length > 0) {
        const recent = data.registration_trends.slice(-7);
        const earlier = data.registration_trends.slice(-14, -7);
        const recentAvg = recent.reduce((a, b) => a + b.value, 0) / recent.length;
        const earlierAvg = earlier.length > 0 ? earlier.reduce((a, b) => a + b.value, 0) / earlier.length : recentAvg;
        const change = earlierAvg > 0 ? ((recentAvg - earlierAvg) / earlierAvg * 100).toFixed(0) : 0;
        const trend = change > 5 ? 'increasing' : change < -5 ? 'decreasing' : 'stable';
        
        insights.push({
            category: 'Growth',
            statement: `Registration activity is ${trend} with an average of ${Math.round(recentAvg)} daily signups over the past week${Math.abs(change) > 5 ? `, ${change > 0 ? 'up' : 'down'} ${Math.abs(change)}% from the previous week` : ''}.`
        });
    }
    
    // 2. User Base Composition
    if (summary && summary.total_users > 0) {
        const orgs = summary.unique_organizations || 0;
        const avgUsersPerOrg = orgs > 0 ? (summary.total_users / orgs).toFixed(1) : 0;
        insights.push({
            category: 'Composition',
            statement: `The platform serves ${summary.total_users.toLocaleString()} users across ${orgs} organizations, averaging ${avgUsersPerOrg} users per organization.`
        });
    }
    
    // 3. Geographic Distribution
    if (data.top_cities && data.top_cities.length > 0) {
        const topCity = data.top_cities[0];
        const top3Cities = data.top_cities.slice(0, 3);
        const top3Total = top3Cities.reduce((a, b) => a + b.value, 0);
        const concentration = summary && summary.total_users > 0 ? ((top3Total / summary.total_users) * 100).toFixed(0) : 0;
        
        insights.push({
            category: 'Geography',
            statement: `${topCity.label} leads with ${topCity.value} users. The top 3 cities account for ${concentration}% of the user base, indicating ${concentration > 40 ? 'strong' : 'moderate'} geographic concentration.`
        });
    }
    
    // 4. Domain Analysis
    if (data.top_domains && data.top_domains.length > 0) {
        const topDomain = data.top_domains[0];
        const top3Domains = data.top_domains.slice(0, 3);
        const top3Total = top3Domains.reduce((a, b) => a + b.value, 0);
        const domainShare = summary && summary.total_users > 0 ? ((topDomain.value / summary.total_users) * 100).toFixed(0) : 0;
        
        insights.push({
            category: 'Sector',
            statement: `${topDomain.label} represents ${domainShare}% of users, with the top 3 domains comprising ${top3Total} total registrations.`
        });
    }
    
    // 5. Gender Distribution
    if (data.gender_distribution && data.gender_distribution.length > 0) {
        const total = data.gender_distribution.reduce((a, b) => a + b.value, 0);
        const male = data.gender_distribution.find(g => g.label.toLowerCase().includes('male'));
        const female = data.gender_distribution.find(g => g.label.toLowerCase().includes('female'));
        
        if (male && female) {
            const malePct = ((male.value / total) * 100).toFixed(0);
            const femalePct = ((female.value / total) * 100).toFixed(0);
            insights.push({
                category: 'Demographics',
                statement: `Gender distribution shows ${malePct}% male and ${femalePct}% female representation, with ${total} users providing gender data.`
            });
        }
    }
    
    // 6. Social Media Engagement
    if (summary && summary.users_with_github !== undefined && summary.users_with_linkedin !== undefined) {
        const total = summary.total_users || 0;
        if (total > 0) {
            const githubPct = ((summary.users_with_github / total) * 100).toFixed(0);
            const linkedinPct = ((summary.users_with_linkedin / total) * 100).toFixed(0);
            const both = summary.users_with_github && summary.users_with_linkedin ? 
                Math.min(summary.users_with_github, summary.users_with_linkedin) : 0;
            const bothPct = ((both / total) * 100).toFixed(0);
            
            insights.push({
                category: 'Engagement',
                statement: `${githubPct}% of users have GitHub profiles, ${linkedinPct}% have LinkedIn profiles, with ${bothPct}% maintaining both platforms.`
            });
        }
    }
    
    // 7. Age Distribution (if available)
    if (data.age_groups && data.age_groups.length > 0) {
        const largestGroup = data.age_groups.reduce((a, b) => a.value > b.value ? a : b);
        const totalAge = data.age_groups.reduce((a, b) => a + b.value, 0);
        const groupPct = ((largestGroup.value / totalAge) * 100).toFixed(0);
        
        insights.push({
            category: 'Demographics',
            statement: `The ${largestGroup.label} age group is the largest segment, representing ${groupPct}% of users with age data.`
        });
    }
    
    // 8. Organization Concentration
    if (data.top_organizations && data.top_organizations.length > 0 && summary) {
        const topOrg = data.top_organizations[0];
        const top3Orgs = data.top_organizations.slice(0, 3);
        const top3Total = top3Orgs.reduce((a, b) => a + b.value, 0);
        const orgConcentration = summary.total_users > 0 ? ((top3Total / summary.total_users) * 100).toFixed(0) : 0;
        
        insights.push({
            category: 'Organizations',
            statement: `${topOrg.label} is the largest organization with ${topOrg.value} users. The top 3 organizations represent ${orgConcentration}% of the user base.`
        });
    }
    
    // Render insights with data intelligence styling
    if (insights.length > 0) {
        insightsList.innerHTML = insights.map(insight => `
            <div class="insight-item">
                <div class="insight-category">${insight.category}</div>
                <div class="insight-statement">${insight.statement}</div>
            </div>
        `).join('');
    } else {
        insightsList.innerHTML = `
            <div class="insight-item">
                <div class="insight-category">Analysis</div>
                <div class="insight-statement">Insufficient data available to generate insights at this time.</div>
            </div>
        `;
    }
}

/**
 * Refresh insights
 */
function refreshInsights() {
    loadDashboardData();
}

/**
 * Toggle data density mode
 */
function toggleDensity() {
    const dashboard = document.querySelector('.dashboard-enterprise');
    const btn = document.getElementById('densityToggle');
    
    if (dashboard) {
        const isCompact = dashboard.classList.contains('compact');
        dashboard.classList.toggle('compact');
        
        if (btn) {
            const span = btn.querySelector('span');
            if (span) {
                span.textContent = isCompact ? 'Compact' : 'Expanded';
            } else {
                btn.textContent = isCompact ? 'Compact' : 'Expanded';
            }
            btn.title = isCompact ? 'Data Density: Compact' : 'Data Density: Expanded';
        }
        
        // Show notification
        showNotification(
            isCompact ? 'Switched to Compact view' : 'Switched to Expanded view',
            'info'
        );
    }
}

/**
 * Open command palette
 */
function openCommandPalette() {
    // Create command palette modal
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.id = 'commandPalette';
    modal.style.display = 'flex';
    
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 600px; width: 90%;">
            <div class="modal-header">
                <h2>Command Palette</h2>
                <button class="modal-close" onclick="closeCommandPalette()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="modal-body">
                <div style="margin-bottom: 16px;">
                    <input type="text" id="commandInput" placeholder="Type a command..." 
                           style="width: 100%; padding: 12px; border: 1px solid var(--glass-border); 
                                  border-radius: 8px; font-size: 14px; font-family: 'Inter', sans-serif;"
                           autofocus>
                </div>
                <div id="commandResults" style="max-height: 400px; overflow-y: auto;">
                    <div class="command-item" data-action="refresh" onclick="executeCommand('refresh')">
                        <i class="fas fa-sync-alt" style="margin-right: 12px; color: var(--accent-blue);"></i>
                        <div>
                            <div style="font-weight: 600; margin-bottom: 4px;">Refresh Dashboard</div>
                            <div style="font-size: 12px; color: var(--text-muted);">Reload all dashboard data</div>
                        </div>
                    </div>
                    <div class="command-item" data-action="export" onclick="executeCommand('export')">
                        <i class="fas fa-download" style="margin-right: 12px; color: var(--accent-blue);"></i>
                        <div>
                            <div style="font-weight: 600; margin-bottom: 4px;">Export Data</div>
                            <div style="font-size: 12px; color: var(--text-muted);">Download dashboard data as CSV</div>
                        </div>
                    </div>
                    <div class="command-item" data-action="period-7d" onclick="executeCommand('period-7d')">
                        <i class="fas fa-calendar-week" style="margin-right: 12px; color: var(--accent-blue);"></i>
                        <div>
                            <div style="font-weight: 600; margin-bottom: 4px;">Last 7 Days</div>
                            <div style="font-size: 12px; color: var(--text-muted);">Filter to last 7 days</div>
                        </div>
                    </div>
                    <div class="command-item" data-action="period-30d" onclick="executeCommand('period-30d')">
                        <i class="fas fa-calendar-alt" style="margin-right: 12px; color: var(--accent-blue);"></i>
                        <div>
                            <div style="font-weight: 600; margin-bottom: 4px;">Last 30 Days</div>
                            <div style="font-size: 12px; color: var(--text-muted);">Filter to last 30 days</div>
                        </div>
                    </div>
                    <div class="command-item" data-action="period-90d" onclick="executeCommand('period-90d')">
                        <i class="fas fa-calendar" style="margin-right: 12px; color: var(--accent-blue);"></i>
                        <div>
                            <div style="font-weight: 600; margin-bottom: 4px;">Last 90 Days</div>
                            <div style="font-size: 12px; color: var(--text-muted);">Filter to last 90 days</div>
                        </div>
                    </div>
                    <div class="command-item" data-action="compact" onclick="executeCommand('compact')">
                        <i class="fas fa-compress" style="margin-right: 12px; color: var(--accent-blue);"></i>
                        <div>
                            <div style="font-weight: 600; margin-bottom: 4px;">Toggle Compact View</div>
                            <div style="font-size: 12px; color: var(--text-muted);">Switch between compact and expanded layout</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Focus input and handle search
    const input = document.getElementById('commandInput');
    if (input) {
        input.addEventListener('input', function(e) {
            filterCommands(e.target.value);
        });
        
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                closeCommandPalette();
            } else if (e.key === 'Enter') {
                const firstItem = document.querySelector('.command-item:not([style*="display: none"])');
                if (firstItem) {
                    firstItem.click();
                }
            }
        });
    }
    
    // Close on backdrop click
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeCommandPalette();
        }
    });
}

/**
 * Close command palette
 */
function closeCommandPalette() {
    const modal = document.getElementById('commandPalette');
    if (modal) {
        modal.remove();
    }
}

/**
 * Filter commands in palette
 */
function filterCommands(query) {
    const items = document.querySelectorAll('.command-item');
    const lowerQuery = query.toLowerCase();
    
    items.forEach(item => {
        const text = item.textContent.toLowerCase();
        if (text.includes(lowerQuery)) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

/**
 * Execute command from palette
 */
function executeCommand(action) {
    closeCommandPalette();
    
    switch(action) {
        case 'refresh':
            loadDashboardData();
            break;
        case 'export':
            exportData();
            break;
        case 'period-7d':
            setPeriod('7d');
            break;
        case 'period-30d':
            setPeriod('30d');
            break;
        case 'period-90d':
            setPeriod('90d');
            break;
        case 'compact':
            toggleDensity();
            break;
    }
}

/**
 * Export dashboard data
 */
async function exportData() {
    try {
        // Show loading state
        const exportBtn = event?.target?.closest('.command-btn') || document.querySelector('.command-btn[onclick="exportData()"]');
        if (exportBtn) {
            const originalText = exportBtn.innerHTML;
            exportBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Exporting...';
            exportBtn.disabled = true;
            
            // Fetch data
            const summaryUrl = `/api/dashboard/summary?period=${currentPeriod}`;
            const chartsUrl = `/api/dashboard/charts?period=${currentPeriod}`;
            
            const [summaryRes, chartsRes] = await Promise.all([
                authenticatedFetch(summaryUrl),
                authenticatedFetch(chartsUrl)
            ]);
            
            const summary = await summaryRes.json();
            const charts = await chartsRes.json();
            
            // Create CSV content
            let csvContent = 'Dashboard Export - ' + new Date().toLocaleString() + '\n\n';
            csvContent += 'Summary Statistics\n';
            csvContent += 'Period,Value\n';
            csvContent += `Total Users,${summary.total_users}\n`;
            csvContent += `Unique Organizations,${summary.unique_organizations}\n`;
            csvContent += `Top Domain,${summary.top_domain}\n`;
            csvContent += `Top City,${summary.top_city}\n\n`;
            
            csvContent += 'Registration Trends\n';
            csvContent += 'Date,Count\n';
            charts.registration_trends.forEach(trend => {
                csvContent += `${trend.date},${trend.value}\n`;
            });
            csvContent += '\n';
            
            csvContent += 'Gender Distribution\n';
            csvContent += 'Gender,Count\n';
            charts.gender_distribution.forEach(g => {
                csvContent += `${g.label},${g.value}\n`;
            });
            csvContent += '\n';
            
            csvContent += 'Top Domains\n';
            csvContent += 'Domain,Count\n';
            charts.top_domains.forEach(d => {
                csvContent += `${d.label},${d.value}\n`;
            });
            csvContent += '\n';
            
            csvContent += 'Top Cities\n';
            csvContent += 'City,Count\n';
            charts.top_cities.forEach(c => {
                csvContent += `${c.label},${c.value}\n`;
            });
            
            // Create blob and download
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', `dashboard-export-${currentPeriod}-${Date.now()}.csv`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            // Reset button
            exportBtn.innerHTML = originalText;
            exportBtn.disabled = false;
            
            // Show success message
            showNotification('Data exported successfully!', 'success');
        }
    } catch (error) {
        console.error('Export failed:', error);
        showNotification('Export failed. Please try again.', 'error');
        const exportBtn = document.querySelector('.command-btn[onclick="exportData()"]');
        if (exportBtn) {
            exportBtn.innerHTML = '<span>Export</span>';
            exportBtn.disabled = false;
        }
    }
}

/**
 * Show notification
 */
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 100px;
        right: 24px;
        background: ${type === 'success' ? 'var(--accent-blue)' : type === 'error' ? 'var(--danger-color)' : 'var(--text-secondary)'};
        color: white;
        padding: 16px 24px;
        border-radius: 12px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
        z-index: 10000;
        font-family: 'Inter', sans-serif;
        font-size: 14px;
        font-weight: 500;
        backdrop-filter: blur(20px);
        animation: slideInRight 0.3s ease;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

/**
 * Refresh insights
 */
function refreshInsights() {
    loadDashboardData();
}

/**
 * Show empty chart message
 */
function showEmptyChart(canvasId, message) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    
    // Destroy existing chart if it exists
    if (charts[canvasId]) {
        charts[canvasId].destroy();
    }
    
    // Clear canvas and show message
    const chartContainer = ctx.parentElement;
    ctx.style.display = 'none';
    
    // Create or update message element
    let messageEl = chartContainer.querySelector('.empty-chart-message');
    if (!messageEl) {
        messageEl = document.createElement('div');
        messageEl.className = 'empty-chart-message';
        messageEl.style.cssText = 'text-align: center; padding: 60px 20px; color: #9AA0A6; font-size: 13px; font-family: "Google Sans", sans-serif;';
        chartContainer.appendChild(messageEl);
    }
    messageEl.textContent = message;
}

/**
 * Render donut chart - Enterprise monochrome style
 */
function renderDonutChart(canvasId, title, data) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    
    // Destroy existing chart if it exists
    if (charts[canvasId]) {
        charts[canvasId].destroy();
    }
    
    // Show canvas
    ctx.style.display = 'block';
    const chartContainer = ctx.parentElement;
    if (chartContainer) {
        // Set explicit height for donut chart
        chartContainer.style.height = '280px';
        chartContainer.style.minHeight = '280px';
        chartContainer.style.maxHeight = '280px';
        ctx.style.height = '280px';
        ctx.style.width = '100%';
    }
    const messageEl = chartContainer ? chartContainer.querySelector('.empty-chart-message') : null;
    if (messageEl) messageEl.remove();
    
    const labels = data.map(item => item.label);
    const values = data.map(item => item.value);
    const total = values.reduce((a, b) => a + b, 0);
    
    // Analytical grayscale with brand accent
    const grayscaleColors = [
        '#E5E7EB', // Light gray
        '#D1D5DB', // Medium-light gray
        '#9CA3AF', // Medium gray
        '#6B7280', // Medium-dark gray
        '#4B5563'  // Dark gray
    ];
    const brandAccent = '#FF6B35'; // Orange brand accent
    
    // Use brand accent for largest segment, grayscale for others
    const sortedIndices = values.map((v, i) => ({ value: v, index: i }))
        .sort((a, b) => b.value - a.value);
    const colors = values.map((_, i) => {
        if (sortedIndices[0].index === i) return brandAccent;
        const rank = sortedIndices.findIndex(item => item.index === i);
        return grayscaleColors[Math.min(rank - 1, grayscaleColors.length - 1)] || '#E5E7EB';
    });
    
    charts[canvasId] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 0, // No borders for analytical look
                borderColor: 'transparent',
                cutout: '70%' // Slightly larger donut for better visibility
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(255, 255, 255, 0.98)',
                    padding: 10,
                    titleFont: {
                        family: 'Inter',
                        size: 12,
                        weight: '600'
                    },
                    bodyFont: {
                        family: 'Inter',
                        size: 11,
                        weight: '500'
                    },
                    borderColor: '#E5E7EB',
                    borderWidth: 1,
                    cornerRadius: 4, // Reduced rounded corners
                    titleColor: '#1F2937',
                    bodyColor: '#6B7280',
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        },
        plugins: [{
            id: 'centerText',
            beforeDraw: function(chart) {
                const ctx = chart.ctx;
                const centerX = chart.chartArea.left + (chart.chartArea.right - chart.chartArea.left) / 2;
                const centerY = chart.chartArea.top + (chart.chartArea.bottom - chart.chartArea.top) / 2;
                
                ctx.save();
                ctx.font = '600 20px Inter';
                ctx.fillStyle = '#1A1A1A';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(total.toString(), centerX, centerY - 6);
                
                ctx.font = '500 10px Inter';
                ctx.fillStyle = '#8A8A8A';
                ctx.textTransform = 'uppercase';
                ctx.letterSpacing = '0.05em';
                ctx.fillText('Total', centerX, centerY + 10);
                ctx.restore();
            }
        }]
    });
}

/**
 * Render bar chart - Professional, high-contrast, data-focused style
 */
function renderBarChart(canvasId, title, data) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    
    // Destroy existing chart if it exists
    if (charts[canvasId]) {
        charts[canvasId].destroy();
    }
    
    // Show canvas and ensure pointer events
    ctx.style.display = 'block';
    ctx.style.pointerEvents = 'auto';
    const chartContainer = ctx.parentElement;
    if (chartContainer) {
        chartContainer.style.pointerEvents = 'auto';
        // Set explicit height for bar charts - increased to accommodate rotated labels
        chartContainer.style.height = '320px';
        chartContainer.style.minHeight = '320px';
        chartContainer.style.maxHeight = '320px';
        ctx.style.height = '320px';
        ctx.style.width = '100%';
    }
    const messageEl = chartContainer.querySelector('.empty-chart-message');
    if (messageEl) messageEl.remove();
    
    const labels = data.map(item => item.label);
    const values = data.map(item => item.value);
    const maxValue = Math.max(...values);
    const minValue = Math.min(...values);
    
    // Analytical grayscale with one brand accent
    // Top value gets brand accent, others use grayscale
    const sortedIndices = values.map((v, i) => ({ value: v, index: i }))
        .sort((a, b) => b.value - a.value);
    
    const brandAccent = '#FF6B35'; // Orange brand accent
    const grayscaleColors = [
        '#E5E7EB', // Light gray
        '#D1D5DB', // Medium-light gray
        '#9CA3AF', // Medium gray
        '#6B7280', // Medium-dark gray
        '#4B5563', // Dark gray
        '#374151'  // Darker gray
    ];
    
    // Assign colors: top value gets accent, others use grayscale
    const backgroundColors = values.map((v, i) => {
        if (sortedIndices[0].index === i) return brandAccent;
        // Use grayscale based on value ranking
        const rank = sortedIndices.findIndex(item => item.index === i);
        const grayIndex = Math.min(rank - 1, grayscaleColors.length - 1);
        return grayscaleColors[grayIndex] || '#E5E7EB';
    });
    
    // Keep full labels - don't truncate, let Chart.js handle wrapping
    const displayLabels = labels;
    
    // Always use rotated labels for better readability with long names
    const needsRotation = true; // Always rotate for better label visibility
    
    // Calculate optimal bar thickness based on container size
    const containerWidth = chartContainer ? chartContainer.offsetWidth : 300;
    const barCount = values.length;
    const optimalBarThickness = Math.min(60, Math.max(30, (containerWidth - 40) / barCount * 0.6));
    
    charts[canvasId] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: displayLabels,
            datasets: [{
                label: title,
                data: values,
                backgroundColor: backgroundColors,
                borderRadius: 0, // No rounded corners - analytical style
                borderSkipped: false,
                maxBarThickness: optimalBarThickness,
                minBarLength: 4,
                borderWidth: 0,
                categoryPercentage: 0.85, // Increased for better data density
                barPercentage: 0.95, // Increased for better data density
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false, /* Use container height to prevent elongation */
            resizeDelay: 100,
            layout: {
                padding: {
                    top: 4,
                    right: 8,
                    bottom: 80, // Increased bottom padding to accommodate rotated labels
                    left: 4
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(255, 255, 255, 0.98)',
                    padding: 10,
                    titleFont: {
                        family: 'Inter',
                        size: 12,
                        weight: '600'
                    },
                    bodyFont: {
                        family: 'Inter',
                        size: 11,
                        weight: '500'
                    },
                    borderColor: '#E5E7EB',
                    borderWidth: 1,
                    cornerRadius: 4, // Reduced rounded corners
                    displayColors: true,
                    titleColor: '#1F2937',
                    bodyColor: '#6B7280',
                    titleMarginBottom: 6,
                    callbacks: {
                        title: function(context) {
                            const index = context[0].dataIndex;
                            return labels[index];
                        },
                        label: function(context) {
                            const value = context.parsed.y;
                            const category = title.toLowerCase().replace('top ', '');
                            return `${value} ${category}`;
                        },
                        labelColor: function(context) {
                            return {
                                borderColor: backgroundColors[context.dataIndex],
                                backgroundColor: backgroundColors[context.dataIndex],
                                borderWidth: 1,
                                borderRadius: 2 // Reduced rounded corners
                            };
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false, // No grid lines on x-axis
                        drawBorder: false
                    },
                    ticks: {
                        font: {
                            family: 'Inter',
                            size: 10,
                            weight: '500'
                        },
                        color: '#6B7280',
                        padding: 8,
                        maxRotation: 45, // Rotate labels 45 degrees
                        minRotation: 45, // Keep consistent rotation
                        autoSkip: false, // Show all labels
                        maxTicksLimit: undefined, // No limit on ticks
                        callback: function(value, index) {
                            // Return full label, Chart.js will handle rotation
                            return displayLabels[index] || '';
                        }
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: '#E5E7EB', // Grayscale grid lines
                        drawBorder: false,
                        lineWidth: 1,
                        drawOnChartArea: true,
                        drawTicks: false
                    },
                    ticks: {
                        font: {
                            family: 'Inter',
                            size: 11,
                            weight: '500'
                        },
                        color: '#6B7280', // Grayscale text
                        padding: 8, // Reduced padding
                        stepSize: undefined,
                        maxTicksLimit: 6, // Limit ticks for better density
                        callback: function(value) {
                            // Format large numbers
                            if (value >= 1000) {
                                return (value / 1000).toFixed(1) + 'k';
                            }
                            return value;
                        }
                    },
                    title: {
                        display: false
                    }
                },
                x: {
                    grid: {
                        display: false,
                        drawBorder: false
                    },
                    ticks: {
                        font: {
                            family: 'Inter',
                            size: 10,
                            weight: '500'
                        },
                        color: '#6B7280', // Grayscale text
                        maxRotation: 45, // Always rotate for better visibility
                        minRotation: 45, // Keep consistent rotation
                        padding: 16, // Increased padding to prevent label cutoff
                        autoSkip: false, // Show all labels
                        maxTicksLimit: undefined, // No limit on ticks
                        callback: function(value, index) {
                            // Return full label without truncation - Chart.js will handle rotation
                            return displayLabels[index] || '';
                        }
                    },
                    offset: true // Add offset to give more space for rotated labels
                }
            }
        }
    });
    
    // Handle container resize for better responsiveness
    if (typeof ResizeObserver !== 'undefined' && chartContainer) {
        const resizeObserver = new ResizeObserver(entries => {
            if (charts[canvasId]) {
                charts[canvasId].resize();
            }
        });
        resizeObserver.observe(chartContainer);
        
        // Store observer for cleanup if needed
        if (!chartContainer._chartResizeObserver) {
            chartContainer._chartResizeObserver = resizeObserver;
        }
    }
}

/**
 * Render line chart - Enterprise monochrome style (daily registration trend)
 */
function renderLineChart(canvasId, title, data) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    
    // Destroy existing chart if it exists
    if (charts[canvasId]) {
        charts[canvasId].destroy();
    }
    
    // Show canvas and ensure pointer events are enabled
    ctx.style.display = 'block';
    ctx.style.pointerEvents = 'auto';
    ctx.style.cursor = 'crosshair';
    const chartContainer = ctx.parentElement;
    if (chartContainer) {
        chartContainer.style.pointerEvents = 'auto';
    }
    const messageEl = chartContainer.querySelector('.empty-chart-message');
    if (messageEl) messageEl.remove();
    
    const labels = data.map(item => item.label);
    const values = data.map(item => item.value);
    const dates = data.map(item => item.date || item.label);
    
    // Calculate step size for x-axis labels
    const labelStep = Math.max(1, Math.floor(labels.length / 10));
    
    // Analytical grayscale with brand accent - no gradient fill
    const brandAccent = '#FF6B35'; // Orange brand accent
    const lineColor = brandAccent; // Use brand accent for line
    const fillColor = 'rgba(255, 107, 53, 0.05)'; // Solid subtle fill - no gradient
    
    // Set container height for line chart
    if (chartContainer) {
        chartContainer.style.height = '350px';
        ctx.height = 350;
    }
    
    charts[canvasId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: title,
                data: values,
                borderColor: lineColor,
                backgroundColor: fillColor,
                fill: true,
                tension: 0.3, // Less curve for analytical look
                pointRadius: 0, // No points by default
                pointHoverRadius: 5,
                pointHitRadius: 8,
                pointBackgroundColor: lineColor,
                pointBorderColor: '#FFFFFF',
                pointBorderWidth: 2,
                pointHoverBackgroundColor: brandAccent,
                pointHoverBorderColor: '#FFFFFF',
                borderWidth: 2.5, // Slightly thicker for visibility
                hoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(255, 255, 255, 0.98)',
                    padding: 10,
                    titleFont: {
                        family: 'Inter',
                        size: 12,
                        weight: '600'
                    },
                    bodyFont: {
                        family: 'Inter',
                        size: 11,
                        weight: '500'
                    },
                    borderColor: '#E5E7EB',
                    borderWidth: 1,
                    cornerRadius: 4, // Reduced rounded corners
                    displayColors: false,
                    titleColor: '#1F2937',
                    bodyColor: '#6B7280',
                    callbacks: {
                        title: function(context) {
                            const index = context[0].dataIndex;
                            if (dates[index]) {
                                try {
                                    const date = new Date(dates[index]);
                                    return date.toLocaleDateString('en-US', { 
                                        month: 'short', 
                                        day: 'numeric', 
                                        year: 'numeric' 
                                    });
                                } catch (e) {
                                    return labels[index];
                                }
                            }
                            return labels[index];
                        },
                        label: function(context) {
                            return `${context.parsed.y} registration${context.parsed.y !== 1 ? 's' : ''}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: '#E5E7EB', // Grayscale grid
                        drawBorder: false,
                        lineWidth: 1,
                        drawTicks: false
                    },
                    ticks: {
                        font: {
                            family: 'Inter',
                            size: 11,
                            weight: '500'
                        },
                        color: '#6B7280', // Grayscale text
                        padding: 8,
                        stepSize: undefined,
                        maxTicksLimit: 6 // Better data density
                    }
                },
                x: {
                    grid: {
                        display: false,
                        drawBorder: false
                    },
                    ticks: {
                        font: {
                            family: 'Inter',
                            size: 11,
                            weight: '500'
                        },
                        color: '#6B7280', // Grayscale text
                        maxRotation: 45,
                        minRotation: 0,
                        padding: 8,
                        callback: function(value, index) {
                            // Show more labels for better data density
                            const step = Math.max(1, Math.floor(labels.length / 12));
                            if (index % step === 0 || index === labels.length - 1) {
                                return labels[index];
                            }
                            return '';
                        }
                    }
                }
            }
        }
    });
}

/**
 * Generate gradient colors for charts
 */
function generateGradientColors(count) {
    const baseColors = [
        '#4285F4', '#34A853', '#FBBC04', '#EA4335', 
        '#9AA0A6', '#5F6368', '#9334E6', '#00BCD4',
        '#FF9800', '#E91E63', '#009688', '#795548'
    ];
    
    const colors = [];
    for (let i = 0; i < count; i++) {
        colors.push(baseColors[i % baseColors.length]);
    }
    return colors;
}

/**
 * Show error message
 */
function showError(message) {
    alert(message); // Can be replaced with a toast notification
}
