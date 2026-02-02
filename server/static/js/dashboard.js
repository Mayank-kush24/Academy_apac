/**
 * Dashboard JavaScript
 */

let charts = {};
let isLoading = false; // Prevent multiple simultaneous loads
let currentPeriod = 'all'; // Default period (entire dataset)

// Load dashboard data on page load
document.addEventListener('DOMContentLoaded', function() {
    // Only load if we're on the dashboard page
    if (window.location.pathname === '/dashboard') {
        // Set active nav item
        setActiveNavItem();
        initializeDashboard();
        loadDashboardData();
        updateHeaderUserInfo(); // Update header user info on load
    }
});

/**
 * Set active navigation item
 */
function setActiveNavItem() {
    // Remove active class from all nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // Add active class to dashboard nav item
    const dashboardNav = document.querySelector('a[href="/dashboard"]');
    if (dashboardNav) {
        dashboardNav.classList.add('active');
    }
}

/**
 * Initialize dashboard interactions
 */
function initializeDashboard() {
    // Time period filter buttons (premium style)
    const periodButtons = document.querySelectorAll('.period-btn[data-period]');
    periodButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const period = this.getAttribute('data-period');
            setPeriod(period);
        });
    });
    
    // Also support old pill class for backward compatibility
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
    
    // Update active button (premium style)
    document.querySelectorAll('.period-btn[data-period]').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('data-period') === period) {
            btn.classList.add('active');
        }
    });
    
    // Also update old pills for backward compatibility
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
    
    // Show loading state (if old structure exists)
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
        } else {
            summary = {
                total_users: 0,
                unique_organizations: 0,
                top_domain: 'N/A',
                top_city: 'N/A',
                average_age: null,
                apac_except_india_users: 0,
                top_india_state: 'N/A',
                top_india_city: 'N/A',
                top_apac_country: 'N/A',
                previous_period_total_users: null,
                previous_period_apac_users: null,
                previous_period_average_age: null
            };
        }
        
        const chartsUrl = `/api/dashboard/charts?period=${currentPeriod}`;
        const chartsResponse = await authenticatedFetch(chartsUrl);
        let chartsData = null;
        if (chartsResponse.ok) {
            chartsData = await chartsResponse.json();
        } else {
            chartsData = { registration_trends: [], gender_distribution: [], top_domains: [], top_cities: [], top_organizations: [] };
        }
        updateKPICards(summary, chartsData);
        renderCharts(chartsData, summary);
    } catch (error) {
        console.error('Failed to load dashboard data:', error);
        // Show empty state instead of error
        updateKPICards({
            total_users: 0,
            unique_organizations: 0,
            top_domain: 'N/A',
            top_city: 'N/A',
            average_age: null,
            apac_except_india_users: 0,
            top_india_state: 'N/A',
            top_india_city: 'N/A',
            top_apac_country: 'N/A'
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
        // Remove loading state (if old structure exists)
        const loadingIndicator = document.querySelector('.command-bar');
        if (loadingIndicator) {
            loadingIndicator.style.opacity = '1';
        }
    }
}

/**
 * Update KPI cards - Premium style with real period-on-period (e.g. week-on-week) numbers
 * @param {Object} summary - summary from API (includes previous_period_* for WoW)
 * @param {Object} [chartsData] - optional charts data for real sparklines (registration_trends)
 */
function updateKPICards(summary, chartsData) {
    const formatNumber = (num) => {
        if (typeof num !== 'number') return num;
        return num.toLocaleString();
    };
    const trendValues = (chartsData && chartsData.registration_trends && Array.isArray(chartsData.registration_trends))
        ? chartsData.registration_trends.map(t => t.value)
        : null;

    const totalUsers = summary.total_users || 0;
    const totalUsersEl = document.getElementById('totalUsers');
    if (totalUsersEl) totalUsersEl.textContent = formatNumber(totalUsers);
    updateKPITrend('totalUsersChange', totalUsers, summary.previous_period_total_users, '—');
    renderMiniChart('totalUsersMiniChart', trendValues && trendValues.length > 0 ? trendValues : generateTrendData(totalUsers));

    const apacUsers = summary.apac_except_india_users || 0;
    const apacUsersEl = document.getElementById('apacUsers');
    if (apacUsersEl) apacUsersEl.textContent = formatNumber(apacUsers);
    updateKPITrend('apacUsersChange', apacUsers, summary.previous_period_apac_users, '—');
    renderMiniChart('apacUsersMiniChart', trendValues && trendValues.length > 0 ? trendValues : generateTrendData(apacUsers));

    const avgAge = summary.average_age;
    const averageAgeEl = document.getElementById('averageAge');
    if (averageAgeEl) {
        if (avgAge && avgAge > 0) averageAgeEl.textContent = Math.round(avgAge) + ' yrs';
        else averageAgeEl.textContent = 'N/A';
    }
    updateKPITrend('averageAgeChange', avgAge || 0, summary.previous_period_average_age, '—');
    renderMiniChart('averageAgeMiniChart', trendValues && trendValues.length > 0 ? trendValues : generateTrendData(avgAge || 0));

    const topIndiaLocationEl = document.getElementById('topIndiaLocation');
    const topIndiaLocationMetaEl = document.getElementById('topIndiaLocationMeta');
    if (topIndiaLocationEl) {
        const state = summary.top_india_state || 'N/A';
        const city = summary.top_india_city || 'N/A';
        if (state !== 'N/A' && city !== 'N/A') topIndiaLocationEl.textContent = `${city}, ${state}`;
        else if (state !== 'N/A') topIndiaLocationEl.textContent = state;
        else if (city !== 'N/A') topIndiaLocationEl.textContent = city;
        else topIndiaLocationEl.textContent = 'N/A';
    }
    if (topIndiaLocationMetaEl) {
        const state = summary.top_india_state || 'N/A';
        const city = summary.top_india_city || 'N/A';
        topIndiaLocationMetaEl.textContent = (state !== 'N/A' && city !== 'N/A') ? `${state} State` : 'India';
    }
    updateKPITrend('topIndiaLocationChange', null, null, '—');

    const topApacCountryEl = document.getElementById('topApacCountry');
    if (topApacCountryEl) topApacCountryEl.textContent = summary.top_apac_country || 'N/A';
    updateKPITrend('topApacCountryChange', null, null, '—');
    renderMiniChart('topApacCountryMiniChart', trendValues && trendValues.length > 0 ? trendValues : generateTrendData(0));

    updateHeaderUserInfo();
}

/**
 * Update KPI trend indicator - real period-on-period (e.g. week-on-week) change
 * @param {string} elementId - ID of the trend element
 * @param {number} current - current period value
 * @param {number|null|undefined} previous - previous period value (same length as current)
 * @param {string} fallbackLabel - if no previous data, e.g. '—' or 'N/A'
 */
function updateKPITrend(elementId, current, previous, fallbackLabel) {
    const trendEl = document.getElementById(elementId);
    if (!trendEl) return;
    if (previous == null || previous === undefined || previous === 0) {
        trendEl.className = 'kpi-change neutral';
        trendEl.innerHTML = `<span>${fallbackLabel !== undefined ? fallbackLabel : '—'}</span>`;
        return;
    }
    const changePct = ((current - previous) / previous) * 100;
    const isPositive = changePct >= 0;
    const sign = changePct >= 0 ? '+' : '';
    const text = `${sign}${changePct.toFixed(1)}%`;
    trendEl.className = `kpi-change ${isPositive ? 'positive' : 'negative'}`;
    trendEl.innerHTML = `
        <i class="fas fa-arrow-${isPositive ? 'up' : 'down'}"></i>
        <span>${text}</span>
    `;
}

/**
 * Generate trend data for mini charts
 */
function generateTrendData(value) {
    // Generate sample trend data (7 points)
    const base = value * 0.7;
    const variation = value * 0.3;
    const data = [];
    for (let i = 0; i < 7; i++) {
        const random = Math.random();
        data.push(Math.round(base + (variation * random)));
    }
    return data;
}

/**
 * Render mini chart for KPI card - Premium style with gradient
 */
function renderMiniChart(canvasId, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !data || data.length === 0) return;
    
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Calculate min/max for scaling
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    
    // Create gradient for line
    const gradient = ctx.createLinearGradient(0, 0, width, 0);
    gradient.addColorStop(0, '#ff7a18');
    gradient.addColorStop(1, '#ff9f43');
    
    // Draw line with gradient
    ctx.strokeStyle = gradient;
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    
    const stepX = width / (data.length - 1);
    data.forEach((value, index) => {
        const x = index * stepX;
        const normalized = (value - min) / range;
        const y = height - (normalized * height * 0.8) - (height * 0.1);
        
        if (index === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    
    ctx.stroke();
    
    // Add subtle glow effect
    ctx.shadowBlur = 4;
    ctx.shadowColor = 'rgba(255, 122, 24, 0.3)';
    ctx.stroke();
    ctx.shadowBlur = 0;
}

/**
 * Update header user info
 */
function updateHeaderUserInfo() {
    try {
        const userStr = localStorage.getItem('user');
        if (userStr) {
            const user = JSON.parse(userStr);
            const userNameEl = document.getElementById('headerUserName');
            const userEmailEl = document.getElementById('headerUserEmail');
            
            if (userNameEl) {
                userNameEl.textContent = user.name || 'User';
            }
            if (userEmailEl) {
                userEmailEl.textContent = user.email || 'user@example.com';
            }
        }
    } catch (e) {
        console.error('Error updating header user info:', e);
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
    
    // Top Domains (Bar Chart) - Primary segmentation
    if (data.top_domains && data.top_domains.length > 0) {
        renderBarChart('domainsChart', 'Top Domains', data.top_domains);
        // Also render for secondary chart if exists
        const secondaryChart = document.getElementById('domainsChartSecondary');
        if (secondaryChart) {
            renderBarChart('domainsChartSecondary', 'Top Domains', data.top_domains);
        }
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
    
    // Render insights with premium data intelligence styling
    if (insights.length > 0) {
        insightsList.innerHTML = insights.map((insight, index) => `
            <div class="insight-item" style="animation-delay: ${index * 0.1}s">
                <div class="insight-icon">
                    <i class="fas fa-lightbulb"></i>
                </div>
                <div class="insight-content">
                    <div class="insight-text">${insight.statement}</div>
                </div>
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
                    <div class="command-item" data-action="period-all" onclick="executeCommand('period-all')">
                        <i class="fas fa-database" style="margin-right: 12px; color: var(--accent-blue);"></i>
                        <div>
                            <div style="font-weight: 600; margin-bottom: 4px;">All Data</div>
                            <div style="font-size: 12px; color: var(--text-muted);">Show entire dataset (no date filter)</div>
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
        case 'period-all':
            setPeriod('all');
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
 * Make it globally accessible
 */
window.exportData = async function exportData(event) {
    try {
        // Show loading state - find button by onclick attribute or class
        let exportBtn = null;
        if (event && event.target) {
            exportBtn = event.target.closest('.action-btn') || 
                       event.target.closest('.command-btn') ||
                       event.target.closest('button');
        }
        if (!exportBtn) {
            exportBtn = document.querySelector('button[onclick="exportData()"]') ||
                       document.querySelector('button[onclick*="exportData"]') ||
                       document.querySelector('.action-btn') ||
                       document.querySelector('.command-btn');
        }
        
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
            csvContent += 'Metric,Value\n';
            csvContent += `Total Users,${summary.total_users}\n`;
            csvContent += `APAC Users (Excl. India),${summary.apac_except_india_users || 0}\n`;
            csvContent += `Average Age,${summary.average_age || 'N/A'}\n`;
            csvContent += `Top India State,${summary.top_india_state || 'N/A'}\n`;
            csvContent += `Top India City,${summary.top_india_city || 'N/A'}\n`;
            csvContent += `Top APAC Country,${summary.top_apac_country || 'N/A'}\n`;
            csvContent += `Unique Organizations,${summary.unique_organizations}\n`;
            csvContent += `Top Domain,${summary.top_domain}\n`;
            csvContent += `Top City,${summary.top_city}\n\n`;
            
            csvContent += 'Registration Trends\n';
            csvContent += 'Date,Count\n';
            if (charts.registration_trends && charts.registration_trends.length > 0) {
                charts.registration_trends.forEach(trend => {
                    const date = trend.date || trend.label || '';
                    csvContent += `${date},${trend.value || 0}\n`;
                });
            }
            csvContent += '\n';
            
            csvContent += 'Gender Distribution\n';
            csvContent += 'Gender,Count\n';
            if (charts.gender_distribution && charts.gender_distribution.length > 0) {
                charts.gender_distribution.forEach(g => {
                    csvContent += `${g.label || 'Unknown'},${g.value || 0}\n`;
                });
            }
            csvContent += '\n';
            
            csvContent += 'Top Domains\n';
            csvContent += 'Domain,Count\n';
            if (charts.top_domains && charts.top_domains.length > 0) {
                charts.top_domains.forEach(d => {
                    csvContent += `${d.label || 'Unknown'},${d.value || 0}\n`;
                });
            }
            csvContent += '\n';
            
            csvContent += 'Top Cities\n';
            csvContent += 'City,Count\n';
            if (charts.top_cities && charts.top_cities.length > 0) {
                charts.top_cities.forEach(c => {
                    csvContent += `${c.label},${c.value}\n`;
                });
            }
            csvContent += '\n';
            
            csvContent += 'Top Organizations\n';
            csvContent += 'Organization,Count\n';
            if (charts.top_organizations && charts.top_organizations.length > 0) {
                charts.top_organizations.forEach(o => {
                    csvContent += `${o.label},${o.value}\n`;
                });
            }
            
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
        } else {
            console.warn('Export button not found');
        }
    } catch (error) {
        console.error('Export failed:', error);
        showNotification('Export failed. Please try again.', 'error');
        // Try to reset button state
        const exportBtn = document.querySelector('button[onclick="exportData()"]') ||
                         document.querySelector('.action-btn[onclick*="exportData"]') ||
                         document.querySelector('.command-btn[onclick*="exportData"]');
        if (exportBtn) {
            exportBtn.innerHTML = '<i class="fas fa-download"></i><span>Export</span>';
            exportBtn.disabled = false;
        }
    }
};

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
        // Set explicit height for donut chart (premium size)
        chartContainer.style.height = '320px';
        chartContainer.style.minHeight = '320px';
        chartContainer.style.maxHeight = '320px';
        ctx.style.height = '320px';
        ctx.style.width = '100%';
    }
    const messageEl = chartContainer ? chartContainer.querySelector('.empty-chart-message') : null;
    if (messageEl) messageEl.remove();
    
    const labels = data.map(item => item.label);
    const values = data.map(item => item.value);
    const total = values.reduce((a, b) => a + b, 0);
    
    // Premium color palette
    const grayscaleColors = [
        'rgba(229, 231, 235, 0.6)', // Light gray with transparency
        'rgba(209, 213, 219, 0.6)', // Medium-light gray
        'rgba(156, 163, 175, 0.6)', // Medium gray
        'rgba(107, 114, 128, 0.6)', // Medium-dark gray
        'rgba(75, 85, 99, 0.6)'  // Dark gray
    ];
    const brandAccent = '#ff7a18'; // Orange primary
    const brandAccentLight = '#ff9f43'; // Orange light
    
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
        // Set explicit height for bar charts (medium size for ranking cards)
        const isRanking = chartContainer.closest('.chart-ranking');
        const height = isRanking ? '280px' : '360px';
        chartContainer.style.height = height;
        chartContainer.style.minHeight = height;
        chartContainer.style.maxHeight = height;
        ctx.style.height = height;
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
    
    const brandAccent = '#ff7a18'; // Orange primary
    const brandAccentLight = '#ff9f43'; // Orange light
    const grayscaleColors = [
        'rgba(229, 231, 235, 0.7)', // Light gray
        'rgba(209, 213, 219, 0.7)', // Medium-light gray
        'rgba(156, 163, 175, 0.7)', // Medium gray
        'rgba(107, 114, 128, 0.7)', // Medium-dark gray
        'rgba(75, 85, 99, 0.7)', // Dark gray
        'rgba(55, 65, 81, 0.7)'  // Darker gray
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
                borderRadius: 8, // Rounded corners for premium look
                borderSkipped: false,
                maxBarThickness: optimalBarThickness,
                minBarLength: 4,
                borderWidth: 0,
                categoryPercentage: 0.8, // Spacing for premium look
                barPercentage: 0.85, // Spacing for premium look
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
                        color: 'rgba(0, 0, 0, 0.04)', // Subtle grid for premium look
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
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.error('Canvas element not found:', canvasId);
        return;
    }
    
    // Destroy existing chart if it exists
    if (charts[canvasId]) {
        charts[canvasId].destroy();
    }
    
    // Show canvas and ensure pointer events are enabled
    canvas.style.display = 'block';
    canvas.style.pointerEvents = 'auto';
    canvas.style.cursor = 'crosshair';
    const chartContainer = canvas.parentElement;
    if (chartContainer) {
        chartContainer.style.pointerEvents = 'auto';
    }
    const messageEl = chartContainer ? chartContainer.querySelector('.empty-chart-message') : null;
    if (messageEl) messageEl.remove();
    
    const labels = data.map(item => item.label);
    const values = data.map(item => item.value);
    const dates = data.map(item => item.date || item.label);
    
    // Calculate step size for x-axis labels
    const labelStep = Math.max(1, Math.floor(labels.length / 10));
    
    // Set container height for line chart (premium large size)
    const chartHeight = 360;
    if (chartContainer) {
        chartContainer.style.height = chartHeight + 'px';
        chartContainer.style.minHeight = chartHeight + 'px';
        chartContainer.style.maxHeight = chartHeight + 'px';
        canvas.style.height = chartHeight + 'px';
        canvas.style.width = '100%';
    }
    
    // Premium gradient colors
    const brandAccent = '#ff7a18'; // Orange primary
    const brandAccentLight = '#ff9f43'; // Orange light
    
    charts[canvasId] = new Chart(canvas, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: title,
                data: values,
                borderColor: brandAccent,
                backgroundColor: function(context) {
                    const chart = context.chart;
                    const ctx = chart.ctx;
                    if (!ctx || typeof ctx.createLinearGradient !== 'function') {
                        return 'rgba(255, 122, 24, 0.15)';
                    }
                    if (!chart.chartArea) {
                        return 'rgba(255, 122, 24, 0.15)';
                    }
                    const gradient = ctx.createLinearGradient(0, chart.chartArea.top, 0, chart.chartArea.bottom);
                    gradient.addColorStop(0, 'rgba(255, 122, 24, 0.15)');
                    gradient.addColorStop(1, 'rgba(255, 122, 24, 0.02)');
                    return gradient;
                },
                fill: true,
                tension: 0.4, // Smooth curves for premium look
                pointRadius: 0, // No points by default
                pointHoverRadius: 6,
                pointHitRadius: 10,
                pointBackgroundColor: brandAccent,
                pointBorderColor: '#FFFFFF',
                pointBorderWidth: 3,
                pointHoverBackgroundColor: brandAccentLight,
                pointHoverBorderColor: '#FFFFFF',
                borderWidth: 3, // Thicker for premium look
                hoverRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
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
                        color: 'rgba(0, 0, 0, 0.04)', // Subtle grid for premium look
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
