/**
 * Dashboard JavaScript
 */

let charts = {};
let isLoading = false;
let currentPeriod = 'all';
let lastLoadedPeriod = null;
let periodDebounceTimer = null;
const PERIOD_DEBOUNCE_MS = 150;

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
            if (period === currentPeriod) return;
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
    
    if (periodDebounceTimer) clearTimeout(periodDebounceTimer);
    periodDebounceTimer = setTimeout(function() {
        periodDebounceTimer = null;
        requestAnimationFrame(function() {
            loadDashboardData();
        });
    }, PERIOD_DEBOUNCE_MS);
}

/**
 * Load dashboard summary and charts (single combined request, cached on server)
 */
async function loadDashboardData() {
    if (isLoading) return;
    if (lastLoadedPeriod === currentPeriod && lastLoadedPeriod !== null) return;
    isLoading = true;

    const loadingIndicator = document.querySelector('.command-bar');
    if (loadingIndicator) loadingIndicator.style.opacity = '0.7';

    try {
        const dataUrl = `/api/dashboard/data?period=${currentPeriod}`;
        const response = await authenticatedFetch(dataUrl);
        let summary = null;
        let chartsData = null;
        if (response.ok) {
            const data = await response.json();
            summary = data.summary || null;
            chartsData = data.charts || null;
        }
        if (!summary) {
            summary = {
                total_users: 0, unique_organizations: 0, top_domain: 'N/A', top_city: 'N/A',
                average_age: null, apac_except_india_users: 0, top_india_state: 'N/A',
                top_india_city: 'N/A', top_apac_country: 'N/A',
                sea_registrations: 0, sea_top_country: 'N/A', anz_registrations: 0, anz_top_country: 'N/A',
                east_asia_registrations: 0, east_asia_top_country: 'N/A', india_registrations: 0,
                total_skillboost_profiles: 0, verified_skillboost_profiles: 0, skillboost_verification_rate: null,
                skillboost_credits_allocated: 0, skillboost_credits_not_sent: 0, skillboost_credits_sent: 0,
                previous_period_total_users: null, previous_period_apac_users: null, previous_period_average_age: null
            };
        }
        if (!chartsData) {
            chartsData = { registration_trends: [], gender_distribution: [], registration_source_bifurcation: [], occupation_distribution: [], top_domains: [], top_cities: [], top_cities_outside_india: [], top_organizations: [], india_state_registrations: [], apac_country_registrations: [] };
        }
        updateKPICards(summary, chartsData);
        renderCharts(chartsData, summary);
        lastLoadedPeriod = currentPeriod;
    } catch (error) {
        console.error('Failed to load dashboard data:', error);
        lastLoadedPeriod = null;
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
            top_apac_country: 'N/A',
            sea_registrations: 0,
            sea_top_country: 'N/A',
            anz_registrations: 0,
            anz_top_country: 'N/A',
            east_asia_registrations: 0,
            east_asia_top_country: 'N/A',
            india_registrations: 0,
            total_skillboost_profiles: 0,
            verified_skillboost_profiles: 0,
            skillboost_verification_rate: null,
            skillboost_credits_allocated: 0,
            skillboost_credits_not_sent: 0,
            skillboost_credits_sent: 0
        });
        renderCharts({
            registration_trends: [],
            gender_distribution: [],
            registration_source_bifurcation: [],
            occupation_distribution: [],
            top_domains: [],
            top_cities: [],
            top_cities_outside_india: [],
            top_organizations: [],
            india_state_registrations: [],
            apac_country_registrations: []
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
    const escapeHtml = (s) => {
        const el = document.createElement('span');
        el.textContent = s;
        return el.innerHTML;
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

    const topIndiaStateLineEl = document.getElementById('topIndiaStateLine');
    const topIndiaCityLineEl = document.getElementById('topIndiaCityLine');
    if (topIndiaStateLineEl) {
        const state = summary.top_india_state || 'N/A';
        const stateCount = summary.top_india_state_count;
        const stateReg = (stateCount != null && stateCount !== undefined) ? formatNumber(stateCount) + ' reg' : '—';
        topIndiaStateLineEl.innerHTML = escapeHtml(state) + ' <span class="kpi-count-muted">: ' + escapeHtml(stateReg) + '</span>';
    }
    if (topIndiaCityLineEl) {
        const city = summary.top_india_city || 'N/A';
        const cityCount = summary.top_india_city_count;
        const cityReg = (cityCount != null && cityCount !== undefined) ? formatNumber(cityCount) + ' reg' : '—';
        topIndiaCityLineEl.innerHTML = escapeHtml(city) + ' <span class="kpi-count-muted">: ' + escapeHtml(cityReg) + '</span>';
    }
    updateKPITrend('topIndiaLocationChange', null, null, '—');

    const topOutsideIndiaCountryLineEl = document.getElementById('topOutsideIndiaCountryLine');
    const topOutsideIndiaCityLineEl = document.getElementById('topOutsideIndiaCityLine');
    if (topOutsideIndiaCountryLineEl) {
        const country = summary.top_apac_country || 'N/A';
        const countryCount = summary.top_apac_country_count;
        const countryReg = (countryCount != null && countryCount !== undefined) ? formatNumber(countryCount) + ' reg' : '—';
        topOutsideIndiaCountryLineEl.innerHTML = escapeHtml(country) + ' <span class="kpi-count-muted">: ' + escapeHtml(countryReg) + '</span>';
    }
    if (topOutsideIndiaCityLineEl && chartsData && Array.isArray(chartsData.top_cities_outside_india) && chartsData.top_cities_outside_india.length > 0) {
        const first = chartsData.top_cities_outside_india[0];
        const label = first.label || '';
        const value = first.value != null && first.value !== undefined ? first.value : 0;
        const regText = formatNumber(value) + ' reg';
        topOutsideIndiaCityLineEl.innerHTML = label ? (escapeHtml(label) + ' <span class="kpi-count-muted">: ' + escapeHtml(regText) + '</span>') : '—';
    } else if (topOutsideIndiaCityLineEl) {
        topOutsideIndiaCityLineEl.textContent = '—';
    }
    updateKPITrend('topApacCountryChange', null, null, '—');
    renderMiniChart('topApacCountryMiniChart', trendValues && trendValues.length > 0 ? trendValues : generateTrendData(0));

    const bookOfBusinessEl = document.getElementById('bookOfBusinessRegistrations');
    if (bookOfBusinessEl) {
        const bobCount = summary.book_of_business_registrations;
        bookOfBusinessEl.textContent = (bobCount !== undefined && bobCount !== null) ? formatNumber(bobCount) : '-';
    }

    const totalSkillboostEl = document.getElementById('totalSkillboostProfiles');
    if (totalSkillboostEl) {
        const total = summary.total_skillboost_profiles;
        totalSkillboostEl.textContent = (total !== undefined && total !== null) ? formatNumber(total) : '-';
    }
    const skillboostMetaEl = document.getElementById('skillboostVerificationMeta');
    if (skillboostMetaEl) {
        const verified = summary.verified_skillboost_profiles;
        const rate = summary.skillboost_verification_rate;
        const total = summary.total_skillboost_profiles;
        if (total !== undefined && total !== null && verified !== undefined && verified !== null) {
            skillboostMetaEl.textContent = 'Verified: ' + formatNumber(verified) + (rate != null ? ' / ' + rate + '%' : '');
        } else {
            skillboostMetaEl.textContent = 'Verified: — / —%';
        }
    }
    const creditsAllocatedEl = document.getElementById('skillboostCreditsAllocated');
    if (creditsAllocatedEl) creditsAllocatedEl.textContent = (summary.skillboost_credits_allocated !== undefined && summary.skillboost_credits_allocated !== null) ? formatNumber(summary.skillboost_credits_allocated) : '-';
    const creditsNotSentEl = document.getElementById('skillboostCreditsNotSent');
    if (creditsNotSentEl) creditsNotSentEl.textContent = (summary.skillboost_credits_not_sent !== undefined && summary.skillboost_credits_not_sent !== null) ? formatNumber(summary.skillboost_credits_not_sent) : '-';
    const creditsSentEl = document.getElementById('skillboostCreditsSent');
    if (creditsSentEl) creditsSentEl.textContent = (summary.skillboost_credits_sent !== undefined && summary.skillboost_credits_sent !== null) ? formatNumber(summary.skillboost_credits_sent) : '-';

    // Region cards: SEA, ANZ, East Asia
    const seaRegEl = document.getElementById('seaRegistrations');
    if (seaRegEl) seaRegEl.textContent = (summary.sea_registrations !== undefined && summary.sea_registrations !== null) ? formatNumber(summary.sea_registrations) : '-';
    const seaTopEl = document.getElementById('seaTopCountry');
    if (seaTopEl) seaTopEl.textContent = 'Top: ' + (summary.sea_top_country || '—');

    const anzRegEl = document.getElementById('anzRegistrations');
    if (anzRegEl) anzRegEl.textContent = (summary.anz_registrations !== undefined && summary.anz_registrations !== null) ? formatNumber(summary.anz_registrations) : '-';
    const anzTopEl = document.getElementById('anzTopCountry');
    if (anzTopEl) anzTopEl.textContent = 'Top: ' + (summary.anz_top_country || '—');

    const eastAsiaRegEl = document.getElementById('eastAsiaRegistrations');
    if (eastAsiaRegEl) eastAsiaRegEl.textContent = (summary.east_asia_registrations !== undefined && summary.east_asia_registrations !== null) ? formatNumber(summary.east_asia_registrations) : '-';
    const eastAsiaTopEl = document.getElementById('eastAsiaTopCountry');
    if (eastAsiaTopEl) eastAsiaTopEl.textContent = 'Top: ' + (summary.east_asia_top_country || '—');

    const indiaRegEl = document.getElementById('indiaRegistrations');
    if (indiaRegEl) indiaRegEl.textContent = (summary.india_registrations !== undefined && summary.india_registrations !== null) ? formatNumber(summary.india_registrations) : '-';
    const indiaTopEl = document.getElementById('indiaTopState');
    if (indiaTopEl) indiaTopEl.textContent = 'Top: ' + (summary.top_india_state || '—');

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
        renderDonutChart('genderChart', 'Gender Distribution', data.gender_distribution, { palette: 'gender' });
    } else {
        showEmptyChart('genderChart', 'No gender data available');
    }
    
    // Registration source bifurcation (Donut: Google vs Hack2skill by UTM medium)
    if (data.registration_source_bifurcation && data.registration_source_bifurcation.length > 0) {
        renderDonutChart('registrationSourceChart', 'Registration source bifurcation', data.registration_source_bifurcation, { palette: 'registration' });
    } else {
        showEmptyChart('registrationSourceChart', 'No registration source data available');
    }
    
    // Top Domains (Bar Chart) - User Segmentation only (no separate Top Domains card)
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

    // Top cities outside India (Bar Chart) – label format "City (Country)"
    if (data.top_cities_outside_india && data.top_cities_outside_india.length > 0) {
        renderBarChart('citiesOutsideIndiaChart', 'Top cities outside India', data.top_cities_outside_india);
    } else {
        showEmptyChart('citiesOutsideIndiaChart', 'No city data outside India');
    }
    
    // Top Organizations (Bar Chart)
    if (data.top_organizations && data.top_organizations.length > 0) {
        renderBarChart('organizationsChart', 'Top Organizations', data.top_organizations);
    } else {
        showEmptyChart('organizationsChart', 'No organization data available');
    }

    // India state-wise heatmap (interactive)
    renderIndiaMapHeatmap(data.india_state_registrations || []);

    // APAC country-wise heatmap (interactive)
    renderApacMapHeatmap(data.apac_country_registrations || []);
    
    // Generate insights (pass both chart data and summary)
    generateInsights(data, summary);
}

/** India GeoJSON URL (states only – no neighboring countries). */
const INDIA_STATES_GEOJSON_URL = 'https://gist.githubusercontent.com/jbrobst/56c13bbbf9d97d187fea01ca62ea5112/raw/e388c4cae20aa53cb5090210a42ebb9b765c0a36/india_states.geojson';

/**
 * Normalize state name for lookup (DB may have "Delhi", GeoJSON has "NCT of Delhi").
 */
function normalizeStateName(name) {
    if (!name || typeof name !== 'string') return '';
    return name.replace(/^NCT of\s+/i, '').trim().toLowerCase();
}

/**
 * Merge Ladakh and Jammu and Kashmir into a single "Jammu and Kashmir" feature (both parts kept, combined).
 * Returns a new features array with the merged feature and the two originals removed.
 */
function mergeLadakhAndJammuKashmir(features) {
    if (!Array.isArray(features)) return features;
    const mergedName = 'Jammu and Kashmir';
    let ladakh = null;
    let jammuKashmir = null;
    const rest = [];
    features.forEach(function (f) {
        const name = (f.properties && f.properties.ST_NM) ? String(f.properties.ST_NM).trim() : '';
        const n = name.toLowerCase();
        if (n === 'ladakh') ladakh = f;
        else if (n === 'jammu and kashmir' || n === 'jammu & kashmir') jammuKashmir = f;
        else rest.push(f);
    });
    if (!ladakh && !jammuKashmir) return features;
    var coords = [];
    if (ladakh && ladakh.geometry && ladakh.geometry.type === 'Polygon' && ladakh.geometry.coordinates) {
        coords.push(ladakh.geometry.coordinates);
    }
    if (jammuKashmir && jammuKashmir.geometry && jammuKashmir.geometry.type === 'Polygon' && jammuKashmir.geometry.coordinates) {
        coords.push(jammuKashmir.geometry.coordinates);
    }
    if (coords.length === 0) return features;
    var merged = {
        type: 'Feature',
        geometry: { type: 'MultiPolygon', coordinates: coords },
        properties: { ST_NM: mergedName }
    };
    rest.push(merged);
    return rest;
}

/**
 * Render interactive India state-wise registration heatmap (India only, no neighbors).
 * @param {Array<{state: string, value: number}>} stateData - From API india_state_registrations
 */
function renderIndiaMapHeatmap(stateData) {
    const container = document.getElementById('indiaMapHeatmap');
    const mapWrap = document.getElementById('indiaMapContainer');
    const tooltipEl = document.getElementById('indiaMapTooltip');
    if (!container || typeof d3 === 'undefined') return;

    container.innerHTML = '';
    const countByState = {};
    (stateData || []).forEach(function (d) {
        const key = normalizeStateName(d.state);
        if (key) countByState[key] = (countByState[key] || 0) + (d.value || 0);
    });
    const values = Object.values(countByState);
    const maxCount = values.length ? Math.max(...values) : 0;

    /** Combined count for merged Jammu and Kashmir (Ladakh + J&K). */
    function countForJammuKashmir() {
        return (countByState['ladakh'] || 0) + (countByState['jammu and kashmir'] || 0) + (countByState['jammu & kashmir'] || 0);
    }

    d3.json(INDIA_STATES_GEOJSON_URL)
        .then(function (geojson) {
            if (!geojson || !geojson.features) {
                container.innerHTML = '<p class="chart-empty">Unable to load India map data.</p>';
                return;
            }
            var features = mergeLadakhAndJammuKashmir(geojson.features);
            const width = Math.min(560, container.clientWidth || 560);
            const height = 380;
            const projection = d3.geoMercator()
                .center([82.5, 22])
                .scale(width * 1.2)
                .translate([width / 2, height / 2]);
            const path = d3.geoPath().projection(projection);
            const colorScale = d3.scaleSequential(d3.interpolateOranges)
                .domain([0, Math.max(maxCount || 1, countForJammuKashmir())]);

            const svg = d3.select(container)
                .append('svg')
                .attr('viewBox', [0, 0, width, height])
                .attr('width', width)
                .attr('height', height);

            const g = svg.append('g');

            g.selectAll('path')
                .data(features)
                .join('path')
                .attr('class', 'state-path')
                .attr('d', path)
                .attr('fill', function (d) {
                    const name = (d.properties && d.properties.ST_NM) ? d.properties.ST_NM : '';
                    const count = (name === 'Jammu and Kashmir') ? countForJammuKashmir() : (countByState[normalizeStateName(name)] || 0);
                    return colorScale(count);
                })
                .attr('stroke', '#000')
                .attr('stroke-width', 1)
                .on('mouseover', function (event, d) {
                    const name = (d.properties && d.properties.ST_NM) ? d.properties.ST_NM : 'Unknown';
                    const count = (name === 'Jammu and Kashmir') ? countForJammuKashmir() : (countByState[normalizeStateName(name)] || 0);
                    if (tooltipEl && mapWrap) {
                        const rect = mapWrap.getBoundingClientRect();
                        tooltipEl.innerHTML = '<span class="tooltip-state">' + name + '</span><div class="tooltip-count">' + count + ' registration' + (count !== 1 ? 's' : '') + '</div>';
                        tooltipEl.classList.add('visible');
                        tooltipEl.style.left = (event.clientX - rect.left + 12) + 'px';
                        tooltipEl.style.top = (event.clientY - rect.top + 12) + 'px';
                    }
                    d3.select(this).classed('highlighted', true);
                })
                .on('mousemove', function (event) {
                    if (tooltipEl && mapWrap) {
                        const rect = mapWrap.getBoundingClientRect();
                        tooltipEl.style.left = (event.clientX - rect.left + 12) + 'px';
                        tooltipEl.style.top = (event.clientY - rect.top + 12) + 'px';
                    }
                })
                .on('mouseout', function () {
                    if (tooltipEl) tooltipEl.classList.remove('visible');
                    d3.select(this).classed('highlighted', false);
                })
                .on('click', function (event, d) {
                    d3.selectAll('#indiaMapHeatmap path.state-path').classed('highlighted', false);
                    d3.select(this).classed('highlighted', true);
                });
        })
        .catch(function () {
            container.innerHTML = '<p class="chart-empty">Unable to load India map.</p>';
        });
}

/** World countries GeoJSON (filter to APAC only). */
var WORLD_COUNTRIES_GEOJSON_URL = 'https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json';

/** APAC country names as they may appear in GeoJSON (lowercase for matching). */
var APAC_GEO_NAMES = new Set([
    'india', 'australia', 'bangladesh', 'bhutan', 'brunei', 'cambodia', 'china', 'fiji',
    'hong kong', 'indonesia', 'japan', 'laos', 'malaysia', 'maldives', 'mongolia', 'myanmar',
    'nepal', 'new zealand', 'north korea', 'pakistan', 'papua new guinea', 'philippines',
    'singapore', 'south korea', 'sri lanka', 'taiwan', 'thailand', 'timor-leste', 'vietnam',
    'korea, republic of', 'lao pdr', 'viet nam', 'brunei darussalam', "democratic people's republic of korea",
    'republic of singapore'
]);

/** Map GeoJSON country name (lowercase) to API lookup key. */
function apacGeoNameToKey(name) {
    var n = (name || '').toLowerCase().trim();
    if (n === 'korea, republic of') return 'south korea';
    if (n === "democratic people's republic of korea") return 'north korea';
    if (n === 'lao pdr') return 'laos';
    if (n === 'viet nam') return 'vietnam';
    if (n === 'brunei darussalam') return 'brunei';
    if (n === 'republic of singapore') return 'singapore';
    return n;
}

/**
 * Render interactive APAC region map: all APAC countries with country-wise registration heatmap.
 * @param {Array<{country: string, value: number}>} countryData - From API apac_country_registrations
 */
function renderApacMapHeatmap(countryData) {
    var container = document.getElementById('apacMapHeatmap');
    var mapWrap = document.getElementById('apacMapContainer');
    var tooltipEl = document.getElementById('apacMapTooltip');
    if (!container || typeof d3 === 'undefined') return;

    container.innerHTML = '';
    var countByCountry = {};
    (countryData || []).forEach(function (d) {
        var key = (d.country || '').toLowerCase().trim();
        if (key) countByCountry[key] = (countByCountry[key] || 0) + (d.value || 0);
    });
    var values = Object.values(countByCountry);
    var maxCount = values.length ? Math.max.apply(null, values) : 0;

    function countForCountry(geoName) {
        var key = apacGeoNameToKey(geoName);
        return countByCountry[key] || 0;
    }

    d3.json(WORLD_COUNTRIES_GEOJSON_URL)
        .then(function (geojson) {
            if (!geojson || !geojson.features) {
                container.innerHTML = '<p class="chart-empty">Unable to load world map data.</p>';
                return;
            }
            /* Exclude India: only show APAC outside India (“Outside Indian Registrations”). */
            function isIndia(geoName) {
                var n = (geoName || '').toLowerCase().trim();
                return n === 'india';
            }
            var apacFeatures = geojson.features.filter(function (f) {
                var name = (f.properties && f.properties.name) ? String(f.properties.name).trim() : '';
                if (isIndia(name)) return false;
                return APAC_GEO_NAMES.has(name.toLowerCase()) || APAC_GEO_NAMES.has(apacGeoNameToKey(name));
            });
            if (apacFeatures.length === 0) {
                container.innerHTML = '<p class="chart-empty">No APAC countries in map data.</p>';
                return;
            }
            var width = Math.min(560, container.clientWidth || 560);
            var height = 380;
            var projection = d3.geoMercator()
                .center([108, 8])
                .scale(width * 0.42)
                .translate([width / 2, height / 2]);
            var path = d3.geoPath().projection(projection);
            /* Color scale: max is top country (no India), so top country = darkest. */
            var maxSqrt = Math.sqrt(Math.max(maxCount || 1, 1));
            var colorScale = d3.scaleSequential(d3.interpolateOranges)
                .domain([0, 1]);
            function colorValue(count) {
                if (count <= 0) return 0;
                var t = Math.sqrt(count) / maxSqrt;
                return 0.2 + 0.8 * Math.min(t, 1);
            }

            var svg = d3.select(container)
                .append('svg')
                .attr('viewBox', [0, 0, width, height])
                .attr('width', width)
                .attr('height', height);

            var g = svg.append('g');

            g.selectAll('path')
                .data(apacFeatures)
                .join('path')
                .attr('class', 'country-path')
                .attr('d', path)
                .attr('fill', function (d) {
                    var name = (d.properties && d.properties.name) ? d.properties.name : '';
                    var count = countForCountry(name);
                    return colorScale(colorValue(count));
                })
                .attr('stroke', '#000')
                .attr('stroke-width', 1)
                .on('mouseover', function (event, d) {
                    var name = (d.properties && d.properties.name) ? d.properties.name : 'Unknown';
                    var count = countForCountry(name);
                    if (tooltipEl && mapWrap) {
                        var rect = mapWrap.getBoundingClientRect();
                        tooltipEl.innerHTML = '<span class="tooltip-state">' + name + '</span><div class="tooltip-count">' + count + ' registration' + (count !== 1 ? 's' : '') + '</div>';
                        tooltipEl.classList.add('visible');
                        tooltipEl.style.left = (event.clientX - rect.left + 12) + 'px';
                        tooltipEl.style.top = (event.clientY - rect.top + 12) + 'px';
                    }
                    d3.select(this).classed('highlighted', true);
                })
                .on('mousemove', function (event) {
                    if (tooltipEl && mapWrap) {
                        var rect = mapWrap.getBoundingClientRect();
                        tooltipEl.style.left = (event.clientX - rect.left + 12) + 'px';
                        tooltipEl.style.top = (event.clientY - rect.top + 12) + 'px';
                    }
                })
                .on('mouseout', function () {
                    if (tooltipEl) tooltipEl.classList.remove('visible');
                    d3.select(this).classed('highlighted', false);
                })
                .on('click', function (event, d) {
                    d3.selectAll('#apacMapHeatmap path.country-path').classed('highlighted', false);
                    d3.select(this).classed('highlighted', true);
                });
        })
        .catch(function () {
            container.innerHTML = '<p class="chart-empty">Unable to load APAC map.</p>';
        });
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
            csvContent += `SEA Registrations,${summary.sea_registrations ?? ''}\n`;
            csvContent += `SEA Top Country,${summary.sea_top_country || 'N/A'}\n`;
            csvContent += `ANZ Registrations,${summary.anz_registrations ?? ''}\n`;
            csvContent += `ANZ Top Country,${summary.anz_top_country || 'N/A'}\n`;
            csvContent += `East Asia Registrations,${summary.east_asia_registrations ?? ''}\n`;
            csvContent += `East Asia Top Country,${summary.east_asia_top_country || 'N/A'}\n`;
            csvContent += `India Registrations,${summary.india_registrations ?? ''}\n`;
            csvContent += `India Top State,${summary.top_india_state || 'N/A'}\n`;
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
 * Render donut chart with optional palette and legend
 * @param {string} canvasId - Canvas element id
 * @param {string} title - Chart title
 * @param {Array<{label: string, value: number}>} data - Chart data
 * @param {{ palette?: 'registration'|'gender'|'occupation' }} [opts] - Options: palette for distinct colors
 */
function renderDonutChart(canvasId, title, data, opts) {
    opts = opts || {};
    const palette = opts.palette || 'gender';
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    const labels = data.map(item => item.label);
    const values = data.map(item => item.value);
    const total = values.reduce((a, b) => a + b, 0);
    var colors;
    if (palette === 'registration') {
        var registrationPalette = { 'Google': '#4285F4', 'Hack2skill': '#ff7a18' };
        colors = labels.map(function (l) { return registrationPalette[l] || '#94a3b8'; });
    } else if (palette === 'occupation') {
        var occupationPalette = ['#059669', '#0ea5e9', '#e11d48', '#6366f1', '#d97706', '#14b8a6', '#8b5cf6', '#f43f5e'];
        colors = labels.map(function (_, i) { return occupationPalette[i % occupationPalette.length]; });
    } else {
        var genderPalette = ['#0d9488', '#7c3aed', '#f59e0b', '#64748b', '#06b6d4'];
        colors = labels.map(function (_, i) { return genderPalette[i % genderPalette.length]; });
    }
    const existing = charts[canvasId];
    if (existing && existing.config && existing.config.type === 'doughnut') {
        existing.data.labels = labels;
        existing.data.datasets[0].data = values;
        existing.data.datasets[0].backgroundColor = colors;
        existing.update('none');
        return;
    }
    if (existing) existing.destroy();
    const donutHeight = 280;
    ctx.style.display = 'block';
    const chartContainer = ctx.parentElement;
    if (chartContainer) {
        chartContainer.style.height = donutHeight + 'px';
        chartContainer.style.minHeight = donutHeight + 'px';
        chartContainer.style.maxHeight = donutHeight + 'px';
        ctx.style.height = donutHeight + 'px';
        ctx.style.width = '100%';
    }
    const messageEl = chartContainer ? chartContainer.querySelector('.empty-chart-message') : null;
    if (messageEl) messageEl.remove();
    charts[canvasId] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 0,
                borderColor: 'transparent',
                cutout: '70%'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            layout: {
                padding: { left: 0, right: 4, top: 0, bottom: 0 }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'right',
                    align: 'center',
                    labels: {
                        padding: 10,
                        usePointStyle: true,
                        pointStyle: 'circle',
                        font: { size: 11, family: 'Inter' },
                        color: '#374151',
                        boxWidth: 12,
                        generateLabels: function(chart) {
                            const data = chart.data;
                            if (data.labels.length && data.datasets.length) {
                                const ds = data.datasets[0];
                                const total = ds.data.reduce(function(a, b) { return a + b; }, 0);
                                return data.labels.map(function(label, i) {
                                    const value = ds.data[i];
                                    const pct = total ? ((value / total) * 100).toFixed(1) : 0;
                                    return {
                                        text: label + ' (' + value + ' – ' + pct + '%)',
                                        fillStyle: ds.backgroundColor[i],
                                        strokeStyle: ds.backgroundColor[i],
                                        index: i
                                    };
                                });
                            }
                            return [];
                        }
                    }
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
    const chartContainer = ctx.parentElement;
    const labels = data.map(item => item.label);
    const values = data.map(item => item.value);
    const sortedIndices = values.map((v, i) => ({ value: v, index: i })).sort((a, b) => b.value - a.value);
    const brandAccent = '#ff7a18';
    const grayscaleColors = ['rgba(229, 231, 235, 0.7)', 'rgba(209, 213, 219, 0.7)', 'rgba(156, 163, 175, 0.7)', 'rgba(107, 114, 128, 0.7)', 'rgba(75, 85, 99, 0.7)', 'rgba(55, 65, 81, 0.7)'];
    const backgroundColors = values.map((v, i) => {
        if (sortedIndices[0].index === i) return brandAccent;
        const rank = sortedIndices.findIndex(item => item.index === i);
        const grayIndex = Math.min(rank - 1, grayscaleColors.length - 1);
        return grayscaleColors[grayIndex] || '#E5E7EB';
    });
    const existing = charts[canvasId];
    if (existing && existing.config && existing.config.type === 'bar') {
        existing.data.labels = labels;
        existing.data.datasets[0].label = title;
        existing.data.datasets[0].data = values;
        existing.data.datasets[0].backgroundColor = backgroundColors;
        existing.update('none');
        return;
    }
    if (existing) existing.destroy();
    ctx.style.display = 'block';
    ctx.style.pointerEvents = 'auto';
    if (chartContainer) {
        chartContainer.style.pointerEvents = 'auto';
        const isRanking = chartContainer.closest('.chart-ranking');
        if (isRanking) {
            ctx.style.height = '100%';
        } else {
            const height = '360px';
            chartContainer.style.height = height;
            chartContainer.style.minHeight = height;
            chartContainer.style.maxHeight = height;
            ctx.style.height = height;
        }
        ctx.style.width = '100%';
    }
    const messageEl = chartContainer ? chartContainer.querySelector('.empty-chart-message') : null;
    if (messageEl) messageEl.remove();
    const containerWidth = chartContainer ? chartContainer.offsetWidth : 300;
    const barCount = values.length;
    const optimalBarThickness = Math.min(60, Math.max(30, (containerWidth - 40) / barCount * 0.6));
    const displayLabels = labels;
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
                    bottom: 120, // Extra space for rotated X-axis labels (e.g. City (Country))
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
    const labels = data.map(item => item.label);
    const values = data.map(item => item.value);
    const existing = charts[canvasId];
    if (existing && existing.config && existing.config.type === 'line') {
        existing.data.labels = labels;
        existing.data.datasets[0].label = title;
        existing.data.datasets[0].data = values;
        existing.update('none');
        return;
    }
    if (existing) existing.destroy();
    canvas.style.display = 'block';
    canvas.style.pointerEvents = 'auto';
    canvas.style.cursor = 'crosshair';
    const chartContainer = canvas.parentElement;
    if (chartContainer) {
        chartContainer.style.pointerEvents = 'auto';
    }
    const messageEl = chartContainer ? chartContainer.querySelector('.empty-chart-message') : null;
    if (messageEl) messageEl.remove();
    
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
