/**
 * Import Data JavaScript
 */

let currentStep = 1;
let excelData = null;
let fieldMappings = {};

function _importAuthHeaders() {
    var t = typeof getAuthToken === 'function' ? getAuthToken() : localStorage.getItem('token');
    var h = {};
    if (t) h['Authorization'] = 'Bearer ' + t;
    return h;
}

function _importFetchUrl(u) {
    if (typeof appUrl === 'function') return appUrl(u);
    return u;
}

function _isCohort3Import() {
    var page = document.querySelector('.import-page');
    if (page && page.getAttribute('data-uts-sync') === '1') return true;
    var fromBody = document.body && document.body.getAttribute('data-cohort-id');
    if (String(fromBody) === '3') return true;
    if (typeof getAppCohortId === 'function' && String(getAppCohortId()) === '3') return true;
    var m = (window.location.pathname || '').match(/\/c\/(\d+)(?:\/|$)/);
    return !!(m && m[1] === '3');
}

function _utsFetchUrl(path) {
    var u = path;
    if (typeof cohortApiUrl === 'function') return cohortApiUrl(u);
    // Fallback when cohort.js not loaded yet: append cohort_id=3
    if (u.indexOf('cohort_id=') === -1 && _isCohort3Import()) {
        u += (u.indexOf('?') >= 0 ? '&' : '?') + 'cohort_id=3';
    }
    return _importFetchUrl(u);
}

function _utsStatusTone(raw) {
    var s = String(raw || '').toLowerCase();
    if (!s || s === '—' || s === '-') return '';
    if (/(ok|success|complete|done)/.test(s)) return 'is-ok';
    if (/(fail|error)/.test(s)) return 'is-error';
    if (/(run|partial|warn)/.test(s)) return 'is-running';
    return '';
}

function _renderUtsStatus(status) {
    status = status || {};
    var elAt = document.getElementById('utsLastSyncAt');
    var elStart = document.getElementById('utsRegistrationStart');
    var elStatus = document.getElementById('utsLastSyncStatus');
    if (elAt) elAt.textContent = status.last_sync_at || 'Never';
    if (elStart) elStart.textContent = status.registration_start || 'No watermark yet';
    if (elStatus) {
        var rawStatus = status.last_sync_status || '—';
        elStatus.textContent = rawStatus;
        elStatus.className = 'uts-metric-value uts-metric-status ' + _utsStatusTone(rawStatus);
    }

    var elGap = document.getElementById('utsGapWarning');
    if (!elGap) return;
    var gaps = status.registration_gaps || [];
    if (!gaps.length) {
        elGap.style.display = 'none';
        elGap.innerHTML = '';
        return;
    }
    var html = '<strong><i class="fas fa-exclamation-triangle"></i> ' +
        'Missing registration window' + (gaps.length > 1 ? 's' : '') + '</strong><ul style="margin: 6px 0 0 18px;">';
    gaps.forEach(function(g) {
        html += '<li>' + escapeHtml(g.from || '?') + ' → ' + escapeHtml(g.to || '?') +
            (g.reason ? '<br><span style="opacity:.75;">' + escapeHtml(g.reason) + '</span>' : '') +
            '</li>';
    });
    html += '</ul>';
    elGap.innerHTML = html;
    elGap.style.display = 'block';
}

async function loadUtsSyncStatus() {
    try {
        var resp = await fetch(_utsFetchUrl('/api/import/uts-sync/status'), {
            headers: _importAuthHeaders(),
            credentials: 'same-origin',
        });
        var data = await resp.json().catch(function() { return {}; });
        if (resp.ok && data.status) _renderUtsStatus(data.status);
    } catch (e) {
        /* ignore status load errors */
    }
}

function _formatUtsResult(data) {
    var lines = [];
    var mode = data.full ? 'full (no start watermark)' : 'incremental (with start)';
    lines.push(data.ok ? 'Sync completed (' + mode + ').' : 'Sync finished with errors (' + mode + ').');
    lines.push('Started: ' + (data.sync_started_at || '—'));
    lines.push('Watermark used: ' + (data.registration_start_used || '(none — full fetch)'));
    lines.push('New watermark: ' + (data.registration_start_new || '—'));
    if (data.registrations_error) {
        lines.push('Registrations — FAILED: ' + data.registrations_error);
    } else {
        var reg = data.registrations || {};
        lines.push(
            'Registrations — fetched: ' + (reg.fetched || 0) +
            ', created: ' + (reg.created || 0) +
            ', updated: ' + (reg.updated || 0) +
            ', skipped: ' + (reg.skipped || 0)
        );
    }
    var mods = data.modules || {};
    if (data.modules_error) {
        lines.push('Modules — FAILED: ' + data.modules_error);
    } else {
        lines.push(
            'Modules — listed: ' + (mods.modules_listed || 0) +
            ', imported: ' + (mods.modules_imported || 0) +
            ', skipped: ' + (mods.modules_skipped || 0) +
            ', unknown: ' + (mods.modules_unknown || 0) +
            ', failed: ' + (mods.modules_failed || 0)
        );
    }
    (data.registration_gaps || []).forEach(function(g) {
        lines.push('Missing window: ' + (g.from || '?') + ' → ' + (g.to || '?'));
    });
    var details = mods.details || [];
    details.slice(0, 40).forEach(function(d) {
        lines.push(
            '  • [' + (d.kind || '?') + '] ' + (d.name || d.id || '') +
            ' → ' + (d.status || '') +
            (d.error ? ' (' + d.error + ')' : '') +
            (d.created != null ? ' c=' + d.created + ' u=' + d.updated : '')
        );
    });
    if (details.length > 40) lines.push('  …and ' + (details.length - 40) + ' more modules');
    return lines.join('\n');
}

async function runUtsSync(full) {
    var btnNow = document.getElementById('utsSyncNowBtn');
    var btnAll = document.getElementById('utsSyncAllBtn');
    var spinner = document.getElementById('utsSyncSpinner');
    var errEl = document.getElementById('utsSyncError');
    var resEl = document.getElementById('utsSyncResult');
    if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }
    if (resEl) { resEl.style.display = 'none'; resEl.textContent = ''; }
    if (btnNow) btnNow.disabled = true;
    if (btnAll) btnAll.disabled = true;
    if (spinner) {
        spinner.style.display = 'inline-flex';
        spinner.innerHTML = full
            ? '<i class="fas fa-spinner fa-spin"></i> Syncing all data… this may take several minutes'
            : '<i class="fas fa-spinner fa-spin"></i> Syncing… this may take a few minutes';
    }
    try {
        var resp = await fetch(_utsFetchUrl('/api/import/uts-sync'), {
            method: 'POST',
            headers: Object.assign({ 'Content-Type': 'application/json' }, _importAuthHeaders()),
            credentials: 'same-origin',
            body: JSON.stringify({ full: !!full }),
        });
        var data = await resp.json().catch(function() { return {}; });
        if (!resp.ok && !data.registrations && !data.modules) {
            throw new Error(data.error || ('Sync failed (HTTP ' + resp.status + ')'));
        }
        if (resEl) {
            resEl.textContent = _formatUtsResult(data);
            resEl.style.display = 'block';
        }
        if (!data.ok && data.error && errEl) {
            errEl.textContent = data.error;
            errEl.style.display = 'block';
        }
        await loadUtsSyncStatus();
    } catch (e) {
        if (errEl) {
            errEl.textContent = (e && e.message) || 'Sync failed';
            errEl.style.display = 'block';
        }
    } finally {
        if (btnNow) btnNow.disabled = false;
        if (btnAll) btnAll.disabled = false;
        if (spinner) spinner.style.display = 'none';
    }
}

function runUtsSyncNow() {
    return runUtsSync(false);
}

function runUtsSyncAll() {
    return runUtsSync(true);
}

(function initCohort3UtsSyncUi() {
    var btn = document.getElementById('utsSyncNowBtn');
    var btnAll = document.getElementById('utsSyncAllBtn');
    if (!btn && !btnAll) return;
    if (btn) btn.addEventListener('click', runUtsSyncNow);
    if (btnAll) btnAll.addEventListener('click', runUtsSyncAll);
    loadUtsSyncStatus();
})();

// Premium file upload zone: show selected file and support drag-and-drop
(function initFileUploadZone() {
    const zone = document.getElementById('fileUploadZone');
    const fileInput = document.getElementById('excelFile');
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    if (!zone || !fileInput || !fileNameDisplay) return;

    function updateZoneFromInput() {
        const file = fileInput.files[0];
        if (file) {
            zone.classList.add('has-file');
            fileNameDisplay.innerHTML = '<i class="fas fa-check-circle"></i> ' + escapeHtml(file.name);
        } else {
            zone.classList.remove('has-file');
            fileNameDisplay.innerHTML = '';
        }
    }

    fileInput.addEventListener('change', updateZoneFromInput);

    ['dragenter', 'dragover'].forEach(ev => {
        zone.addEventListener(ev, function(e) {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.add('drag-over');
        });
    });
    ['dragleave', 'drop'].forEach(ev => {
        zone.addEventListener(ev, function(e) {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('drag-over');
        });
    });
    zone.addEventListener('drop', function(e) {
        const files = e.dataTransfer && e.dataTransfer.files;
        if (files && files.length) {
            fileInput.files = files;
            updateZoneFromInput();
        }
    });

    zone.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            fileInput.click();
        }
    });
})();

// Handle file upload
(function initUploadForm() {
    var uploadForm = document.getElementById('uploadForm');
    if (!uploadForm) return;
    uploadForm.addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const fileInput = document.getElementById('excelFile');
    const file = fileInput.files[0];
    
    if (!file) {
        showError('uploadError', 'Please select a file');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch(_importFetchUrl(cohortApiUrl('/api/import/preview')), {
            method: 'POST',
            headers: _importAuthHeaders(),
            credentials: 'same-origin',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Upload failed');
        }
        
        excelData = await response.json();
        fieldMappings = excelData.auto_mappings;
        
        renderMappingTable();
        goToStep(2);
        
    } catch (error) {
        showError('uploadError', error.message);
    }
    });
})();

/**
 * Render field mapping table
 */
function renderMappingTable() {
    const tbody = document.getElementById('mappingTableBody');
    const dbFields = excelData.db_fields;
    
    tbody.innerHTML = excelData.excel_columns.map((col, index) => {
        const sampleValue = excelData.preview_rows[0] && excelData.preview_rows[0][col] 
            ? String(excelData.preview_rows[0][col]).substring(0, 50) 
            : '';
        
        const currentMapping = fieldMappings[col] || '';
        
        return `
            <tr>
                <td><strong>${escapeHtml(col)}</strong></td>
                <td class="text-muted">${escapeHtml(sampleValue)}</td>
                <td>
                    <select class="mapping-select" data-column="${escapeHtml(col)}" onchange="updateMapping('${escapeHtml(col)}', this.value)">
                        <option value="">-- Skip this column --</option>
                        ${dbFields.map(field => `
                            <option value="${field}" ${currentMapping === field ? 'selected' : ''}>${field}</option>
                        `).join('')}
                    </select>
                </td>
            </tr>
        `;
    }).join('');
}

/**
 * Update field mapping
 */
function updateMapping(column, dbField) {
    if (dbField) {
        fieldMappings[column] = dbField;
    } else {
        delete fieldMappings[column];
    }
}

/**
 * Initialize import mode selection
 */
function initImportModeSelection() {
    // Remove any existing selected state
    document.querySelectorAll('.import-mode-option').forEach(opt => {
        opt.classList.remove('selected');
    });
    
    // Set default selection
    const defaultOption = document.querySelector('.import-mode-option[data-mode="create"]');
    if (defaultOption) {
        defaultOption.classList.add('selected');
        // Also set the hidden radio button
        const radio = defaultOption.querySelector('input[type="radio"]');
        if (radio) radio.checked = true;
    }
    
    // Add click handlers to mode options
    document.querySelectorAll('.import-mode-option').forEach(option => {
        // Remove any existing event listeners by using a flag
        if (option.dataset.listenerAdded) return;
        option.dataset.listenerAdded = 'true';
        
        // Add click handler
        option.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            // Remove selected class from all options
            document.querySelectorAll('.import-mode-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            
            // Add selected class to clicked option
            this.classList.add('selected');
            
            // Update hidden radio button
            const mode = this.getAttribute('data-mode');
            const radio = this.querySelector('input[type="radio"]');
            if (radio) {
                radio.checked = true;
            } else {
                // Fallback: find radio by value
                const fallbackRadio = document.querySelector(`input[name="importMode"][value="${mode}"]`);
                if (fallbackRadio) fallbackRadio.checked = true;
            }
        });
    });
}

/**
 * Navigate to step
 */
function goToStep(step) {
    // Hide all steps
    document.querySelectorAll('.wizard-step').forEach(s => {
        s.style.display = 'none';
        s.classList.remove('active');
    });
    
    // Show target step
    const targetStep = document.getElementById(`step${step}`);
    if (targetStep) {
        targetStep.style.display = 'block';
        targetStep.classList.add('active');
        currentStep = step;
    }
    
    // Initialize import mode selection when step 3 is shown
    if (step === 3) {
        setTimeout(() => {
            initImportModeSelection();
        }, 100);
    }
}

/**
 * Set import overlay phase: 'parsing' | 'importing'
 */
function setImportPhase(phase) {
    const titleText = document.getElementById('importProgressTitleText');
    const subtitle = document.getElementById('importProgressSubtitle');
    const titleIcon = document.querySelector('#importProgressTitle i');
    if (phase === 'parsing') {
        if (titleText) titleText.textContent = 'Parsing file...';
        if (subtitle) subtitle.textContent = 'Reading Excel and preparing import. This may take a moment for large files.';
        if (titleIcon) titleIcon.className = 'fas fa-file-excel fa-spin';
    } else {
        if (titleText) titleText.textContent = 'Importing...';
        if (subtitle) subtitle.textContent = 'Processing rows. Created / Updated / Skipped are updated below.';
        if (titleIcon) titleIcon.className = 'fas fa-sync-alt fa-spin';
    }
}

/**
 * Show import progress overlay and update stats
 */
function showImportProgressOverlay() {
    const overlay = document.getElementById('importProgressOverlay');
    const btn = document.getElementById('executeImportBtn');
    if (overlay) overlay.style.display = 'flex';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Importing...';
    }
    setImportPhase('parsing');
    setImportProgressStats(0, 0, 0);
    const bar = document.getElementById('importProgressBar');
    if (bar) {
        bar.classList.add('indeterminate');
        bar.style.width = '0%';
    }
}

/**
 * Hide import progress overlay and reset button
 */
function hideImportProgressOverlay() {
    const overlay = document.getElementById('importProgressOverlay');
    const btn = document.getElementById('executeImportBtn');
    if (overlay) overlay.style.display = 'none';
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-play"></i> Execute Import';
    }
    const bar = document.getElementById('importProgressBar');
    if (bar) bar.classList.remove('indeterminate');
}

/**
 * Update progress stats (Created / Updated / Skipped)
 */
function setImportProgressStats(created, updated, skipped) {
    const elCreated = document.getElementById('importStatCreated');
    const elUpdated = document.getElementById('importStatUpdated');
    const elSkipped = document.getElementById('importStatSkipped');
    if (elCreated) elCreated.textContent = created.toLocaleString();
    if (elUpdated) elUpdated.textContent = updated.toLocaleString();
    if (elSkipped) elSkipped.textContent = skipped.toLocaleString();
}

/**
 * Execute import (with streaming progress)
 */
async function executeImport() {
    const selectedOption = document.querySelector('.import-mode-option.selected');
    let mode;
    if (selectedOption) {
        mode = selectedOption.getAttribute('data-mode');
    } else {
        const radio = document.querySelector('input[name="importMode"]:checked');
        mode = radio ? radio.value : 'create';
    }

    if (!excelData || !fieldMappings) {
        alert('Please complete the previous steps');
        return;
    }

    const fileInput = document.getElementById('excelFile');
    const file = fileInput && fileInput.files[0];
    if (!file) {
        alert('File is required');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('mappings', JSON.stringify(fieldMappings));
    formData.append('mode', mode);

    showImportProgressOverlay();

    try {
        const response = await fetch(_importFetchUrl(cohortApiUrl('/api/import/execute?stream=1')), {
            method: 'POST',
            headers: _importAuthHeaders(),
            credentials: 'same-origin',
            body: formData
        });

        if (!response.ok) {
            const err = await response.json().catch(function() { return {}; });
            throw new Error(err.error || 'Import failed');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let result = null;
        let phaseSet = false;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop() || '';
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                const dataMatch = line.match(/^data:\s*(.+)$/m);
                if (!dataMatch) continue;
                try {
                    const data = JSON.parse(dataMatch[1].trim());
                    if (data.error) {
                        throw new Error(data.error);
                    }
                    if (data.total_rows !== undefined && data.created !== undefined && data.updated !== undefined && data.skipped !== undefined) {
                        result = data;
                    } else if (typeof data.created === 'number' || typeof data.updated === 'number' || typeof data.skipped === 'number') {
                        if (!phaseSet) {
                            setImportPhase('importing');
                            phaseSet = true;
                        }
                        setImportProgressStats(data.created || 0, data.updated || 0, data.skipped || 0);
                    } else if (data.created !== undefined || data.updated !== undefined || data.skipped !== undefined) {
                        if (!phaseSet) {
                            setImportPhase('importing');
                            phaseSet = true;
                        }
                        setImportProgressStats(data.created || 0, data.updated || 0, data.skipped || 0);
                    }
                } catch (e) {
                    if (e instanceof SyntaxError) continue;
                    throw e;
                }
            }
        }

        if (buffer) {
            const dataMatch = buffer.match(/^data:\s*(.+)$/m);
            if (dataMatch) {
                try {
                    const data = JSON.parse(dataMatch[1].trim());
                    if (data.error) throw new Error(data.error);
                    if (data.total_rows !== undefined && data.created !== undefined) {
                        result = data;
                        setImportPhase('importing');
                        setImportProgressStats(data.created || 0, data.updated || 0, data.skipped || 0);
                    } else if (data.created !== undefined) {
                        if (!phaseSet) setImportPhase('importing');
                        setImportProgressStats(data.created || 0, data.updated || 0, data.skipped || 0);
                    }
                } catch (e) {
                    if (!(e instanceof SyntaxError)) throw e;
                }
            }
        }

        hideImportProgressOverlay();
        if (result) {
            displayResults(result);
            goToStep(4);
        } else {
            alert('Import completed but no result was received.');
        }
    } catch (error) {
        hideImportProgressOverlay();
        alert('Import failed: ' + (error.message || error));
    }
}

/**
 * Display import results
 */
function displayResults(result) {
    const resultsDiv = document.getElementById('importResults');
    
    const successRate = result.total_rows > 0 
        ? ((result.created + result.updated) / result.total_rows * 100).toFixed(1)
        : 0;
    
    resultsDiv.innerHTML = `
        <div class="results-summary">
            <div class="result-card success">
                <h3>${result.created}</h3>
                <p>Created</p>
            </div>
            <div class="result-card info">
                <h3>${result.updated}</h3>
                <p>Updated</p>
            </div>
            <div class="result-card warning">
                <h3>${result.skipped}</h3>
                <p>Skipped</p>
            </div>
            <div class="result-card">
                <h3>${result.total_rows}</h3>
                <p>Total Rows</p>
            </div>
        </div>
        
        ${result.errors && result.errors.length > 0 ? `
            <div class="errors-section">
                <h3>Errors (${result.errors.length})</h3>
                <div class="error-list">
                    ${result.errors.map(error => `<div class="error-item">${escapeHtml(error)}</div>`).join('')}
                </div>
            </div>
        ` : ''}
    `;
}

/**
 * Reset wizard
 */
function resetWizard() {
    currentStep = 1;
    excelData = null;
    fieldMappings = {};
    document.getElementById('uploadForm').reset();
    var zone = document.getElementById('fileUploadZone');
    var fileNameDisplay = document.getElementById('fileNameDisplay');
    if (zone) zone.classList.remove('has-file');
    if (fileNameDisplay) fileNameDisplay.innerHTML = '';
    goToStep(1);
}

/**
 * Utility functions
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showError(elementId, message) {
    const errorDiv = document.getElementById(elementId);
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
    }
}

// Tracks the latest preview state so the upload handler can read whether the
// user explicitly confirmed an "import anyway" with critical sheets missing.
window.skillboostPreviewState = window.skillboostPreviewState || {
    requiresConfirmation: false,
    confirmed: false,
    missingCritical: [],
    sheetMapping: [],
};

function _moduleLabelForRow(row) {
    if (!row) return '';
    if (row.label) {
        if (row.lab != null && row.track != null) return row.label;
        if (row.track != null && row.label.indexOf('Track ' + row.track) === -1) {
            return row.label + ' (Track ' + row.track + ')';
        }
        return row.label;
    }
    if (row.module) return row.module;
    return '';
}

function _renderSheetMappingTable(mapping) {
    if (!mapping || mapping.length === 0) {
        return '<div class="text-muted" style="margin-top: 8px;">No worksheets found.</div>';
    }
    var rows = mapping.map(function(r) {
        var status = r.status || 'unrecognised';
        var statusBadge;
        if (status === 'detected') {
            statusBadge = '<span style="color:#22c55e;font-weight:600;"><i class="fas fa-check-circle"></i> Detected</span>';
        } else if (status === 'duplicate') {
            statusBadge = '<span style="color:#f59e0b;font-weight:600;"><i class="fas fa-clone"></i> Duplicate (ignored)</span>';
        } else {
            statusBadge = '<span style="color:#94a3b8;font-weight:600;"><i class="fas fa-circle-minus"></i> Will be ignored</span>';
        }
        var label = _moduleLabelForRow(r);
        return '<tr>' +
            '<td style="padding:6px 10px;border-bottom:1px solid rgba(255,255,255,0.06);font-family:monospace;">' + escapeHtml(r.sheet_name || '') + '</td>' +
            '<td style="padding:6px 10px;border-bottom:1px solid rgba(255,255,255,0.06);">' + (label ? escapeHtml(label) : '<span class="text-muted">—</span>') + '</td>' +
            '<td style="padding:6px 10px;border-bottom:1px solid rgba(255,255,255,0.06);">' + statusBadge + '</td>' +
            '</tr>';
    }).join('');
    return '<div style="margin-top:10px;max-height:280px;overflow:auto;border:1px solid rgba(255,255,255,0.08);border-radius:6px;">' +
        '<table style="width:100%;border-collapse:collapse;font-size:0.92em;">' +
        '<thead><tr style="background:rgba(255,255,255,0.04);text-align:left;">' +
        '<th style="padding:6px 10px;">Tab name</th>' +
        '<th style="padding:6px 10px;">Mapped module</th>' +
        '<th style="padding:6px 10px;">Status</th>' +
        '</tr></thead>' +
        '<tbody>' + rows + '</tbody></table></div>';
}

function _renderMissingCriticalBanner(missing) {
    if (!missing || missing.length === 0) {
        return '<div style="margin-top:10px;padding:10px 12px;border-radius:6px;background:rgba(34,197,94,0.10);border:1px solid rgba(34,197,94,0.35);color:#86efac;">' +
            '<i class="fas fa-check-circle"></i> All expected modules detected for this cohort.' +
            '</div>';
    }
    var listItems = missing.map(function(m) {
        var label = m.label || m.module || '';
        return '<li style="color:#78350f;"><strong style="color:#451a03;">' + escapeHtml(label) + '</strong> NOT found — this module will not be imported.</li>';
    }).join('');
    return '<div style="margin-top:10px;padding:12px 14px;border-radius:6px;background:#fffbeb;border:1px solid #f59e0b;box-shadow:0 1px 2px rgba(0,0,0,0.06);color:#78350f;">' +
        '<div style="font-weight:600;margin-bottom:6px;color:#451a03;"><i class="fas fa-exclamation-triangle" style="color:#b45309;"></i> ' +
        missing.length + ' expected sheet' + (missing.length === 1 ? '' : 's') + ' missing from this workbook</div>' +
        '<ul style="margin:6px 0 8px 22px;padding:0;line-height:1.55;color:#78350f;">' + listItems + '</ul>' +
        '<label style="display:flex;align-items:center;gap:8px;margin-top:10px;cursor:pointer;color:#451a03;font-weight:500;">' +
        '<input type="checkbox" id="skillboostConfirmMissing" />' +
        '<span>Import anyway (skip these missing modules)</span>' +
        '</label>' +
        '</div>';
}

function _setSkillboostUploadEnabled(enabled) {
    var btn = document.getElementById('skillboostUploadBtn');
    if (!btn) return;
    btn.disabled = !enabled;
    if (enabled) {
        btn.classList.remove('disabled');
    } else {
        btn.classList.add('disabled');
    }
}

var SKILLBOOST_REASON_LABELS = {
    missing_email: 'Missing email',
    invalid_email: 'Invalid email',
    profile_verified_no_update: 'Already verified — row left unchanged (valid=TRUE)',
    duplicate_row_in_workbook: 'Duplicate row in this file (same email + profile link)',
    fk_user_pii_missing: 'Leader email not in user_pii (auto-PII insert also failed)',
    unique_constraint_violation: 'Duplicate / unique constraint violation',
    value_too_long: 'Value too long for column',
    data_type_error: 'Wrong data type for column',
    integrity_error: 'Database integrity error',
    other: 'Other / unclassified',
};

function _formatReasonCode(code) {
    return SKILLBOOST_REASON_LABELS[code] || code || 'other';
}

/** Matches legacy API error lines for rows that were skipped intentionally (not failures). */
function _isInformationalSkillboostProfileErrorLine(s) {
    return typeof s === 'string' && s.indexOf('[profile_verified_no_update]') !== -1;
}

function _moduleLabelForBlock(block) {
    if (!block) return '';
    var base = block.module || '';
    var pretty = base
        .replace(/_/g, ' ')
        .replace(/\b\w/g, function(c) { return c.toUpperCase(); });
    var extras = [];
    if (block.track != null) extras.push('Track ' + block.track);
    if (block.lab != null) extras.push('Lab ' + block.lab);
    var sheet = block.sheet_name || '';
    var label = pretty + (extras.length ? ' (' + extras.join(', ') + ')' : '');
    return sheet ? label + ' — ' + sheet : label;
}

function _csvEscape(value) {
    if (value == null) return '';
    var s = String(value);
    if (s.indexOf('"') !== -1 || s.indexOf(',') !== -1 || s.indexOf('\n') !== -1) {
        return '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
}

function _buildPerSheetErrorsCsv(perSheetErrors) {
    var headers = ['module', 'track', 'lab', 'sheet_name', 'row', 'reason_code', 'reason_message', 'raw_email'];
    var lines = [headers.join(',')];
    (perSheetErrors || []).forEach(function(block) {
        var rows = block && block.rows ? block.rows : [];
        rows.forEach(function(r) {
            lines.push([
                _csvEscape(block.module),
                _csvEscape(block.track != null ? block.track : ''),
                _csvEscape(block.lab != null ? block.lab : ''),
                _csvEscape(block.sheet_name || ''),
                _csvEscape(r.row != null ? r.row : ''),
                _csvEscape(r.reason_code || 'other'),
                _csvEscape(r.reason_message || ''),
                _csvEscape(r.raw_email || ''),
            ].join(','));
        });
    });
    return lines.join('\n');
}

function _downloadCsv(filename, content) {
    try {
        var blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        setTimeout(function() {
            try { document.body.removeChild(a); } catch (e) { /* ignore */ }
            try { URL.revokeObjectURL(url); } catch (e) { /* ignore */ }
        }, 200);
    } catch (e) { /* ignore */ }
}

function renderPerSheetErrorsPanel(perSheetErrors) {
    var container = document.getElementById('skillboostPerSheetErrors');
    if (!container) return;
    if (!perSheetErrors || perSheetErrors.length === 0) {
        container.innerHTML = '';
        container.style.display = 'none';
        return;
    }
    var totalSkipped = 0;
    var totalAutoCreated = 0;
    var blocksWithIssues = [];
    perSheetErrors.forEach(function(b) {
        totalSkipped += (b.skipped || 0);
        totalAutoCreated += (b.pii_auto_created || 0);
        if ((b.rows && b.rows.length > 0) || (b.skipped || 0) > 0) {
            blocksWithIssues.push(b);
        }
    });
    if (blocksWithIssues.length === 0 && totalAutoCreated === 0) {
        container.innerHTML = '';
        container.style.display = 'none';
        return;
    }

    var html = '<details open style="border:1px solid rgba(255,255,255,0.10);border-radius:8px;background:var(--glass-bg, rgba(255,255,255,0.04));">' +
        '<summary style="padding:10px 14px;cursor:pointer;font-weight:600;">' +
        '<i class="fas fa-list-check"></i> Skips &amp; issues by sheet' +
        ' <span class="text-muted" style="font-weight:400;">(' + blocksWithIssues.length + ' sheet' + (blocksWithIssues.length === 1 ? '' : 's') +
        ', ' + totalSkipped.toLocaleString() + ' skipped row' + (totalSkipped === 1 ? '' : 's') +
        (totalAutoCreated > 0 ? ', ' + totalAutoCreated.toLocaleString() + ' user_pii auto-created' : '') +
        ')</span>' +
        ' <button type="button" class="btn btn-sm btn-secondary" id="skillboostDownloadErrorCsvBtn" style="margin-left:12px;">' +
        '<i class="fas fa-download"></i> Download error report (CSV)</button>' +
        '</summary>' +
        '<div style="padding:8px 14px 14px 14px;">' +
        '<p class="text-muted" style="font-size:0.9em;margin:0 0 10px 0;line-height:1.45;">' +
        '<strong>Skipped</strong> is not always a problem: e.g. profiles that are already <strong>verified</strong> ' +
        'are intentionally left unchanged. The table below explains each reason and shows sample Excel row numbers ' +
        '(row 1 = header).</p>';

    perSheetErrors.forEach(function(block) {
        var skipped = block.skipped || 0;
        var autoCreated = block.pii_auto_created || 0;
        var byReason = block.by_reason || [];
        if (skipped === 0 && autoCreated === 0 && byReason.length === 0) return;

        html += '<div style="margin-top:10px;padding:10px 12px;border-radius:6px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">';
        html += '<div style="font-weight:600;">' + escapeHtml(_moduleLabelForBlock(block)) + '</div>';
        html += '<div class="text-muted" style="font-size:0.9em;margin-top:2px;">' +
            (block.created || 0) + ' created · ' +
            (block.updated || 0) + ' updated · ' +
            '<span style="color:#fca5a5;">' + skipped + ' skipped</span>' +
            (autoCreated > 0 ? ' · <span style="color:#86efac;">' + autoCreated + ' user_pii auto-created</span>' : '') +
            '</div>';
        if (byReason.length > 0) {
            html += '<table style="width:100%;border-collapse:collapse;font-size:0.9em;margin-top:8px;">' +
                '<thead><tr style="text-align:left;color:#cbd5e1;">' +
                '<th style="padding:4px 8px;border-bottom:1px solid rgba(255,255,255,0.08);">Reason</th>' +
                '<th style="padding:4px 8px;border-bottom:1px solid rgba(255,255,255,0.08);width:80px;">Count</th>' +
                '<th style="padding:4px 8px;border-bottom:1px solid rgba(255,255,255,0.08);">Sample rows</th>' +
                '</tr></thead><tbody>';
            byReason.forEach(function(r) {
                html += '<tr>' +
                    '<td style="padding:4px 8px;border-bottom:1px solid rgba(255,255,255,0.05);">' + escapeHtml(_formatReasonCode(r.reason_code)) + '</td>' +
                    '<td style="padding:4px 8px;border-bottom:1px solid rgba(255,255,255,0.05);">' + (r.count || 0) + '</td>' +
                    '<td style="padding:4px 8px;border-bottom:1px solid rgba(255,255,255,0.05);font-family:monospace;color:#cbd5e1;">' +
                    ((r.sample_rows || []).join(', ') || '—') + '</td>' +
                    '</tr>';
            });
            html += '</tbody></table>';
            var sumReasons = byReason.reduce(function(acc, r) { return acc + (r.count || 0); }, 0);
            if (skipped > 0 && sumReasons < skipped) {
                html += '<p class="text-muted" style="font-size:0.85em;margin:8px 0 0 0;">' +
                    'Note: only the first ~2000 skipped rows are logged with samples; reason counts may be partial (' +
                    sumReasons.toLocaleString() + ' of ' + skipped.toLocaleString() +
                    '). Download CSV for all logged rows.</p>';
            }
        } else if (skipped > 0) {
            html += '<p style="font-size:0.9em;margin-top:8px;color:#fcd34d;">' +
                'This sheet reported ' + skipped + ' skipped row(s), but no per-reason breakdown was returned. ' +
                'Try upgrading the server import, or check the legacy error list above.</p>';
        }
        html += '</div>';
    });

    html += '</div></details>';
    container.innerHTML = html;
    container.style.display = 'block';

    var btn = document.getElementById('skillboostDownloadErrorCsvBtn');
    if (btn) {
        btn.addEventListener('click', function(ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var csv = _buildPerSheetErrorsCsv(perSheetErrors);
            var ts = new Date().toISOString().replace(/[:.]/g, '-');
            _downloadCsv('action_center_import_errors_' + ts + '.csv', csv);
        });
    }
}

// Skill Lab: run preview and show subsheet/sheet/row info (called automatically when file is selected)
async function runSkillboostPreview(file) {
    const previewResultEl = document.getElementById('skillboostPreviewResult');
    const errorEl = document.getElementById('skillboostUploadError');
    window.skillboostPreviewState = {
        requiresConfirmation: false,
        confirmed: false,
        missingCritical: [],
        sheetMapping: [],
    };
    _setSkillboostUploadEnabled(true);
    if (!file) {
        if (previewResultEl) previewResultEl.style.display = 'none';
        return;
    }
    if (errorEl) errorEl.style.display = 'none';
    if (previewResultEl) { previewResultEl.style.display = 'block'; previewResultEl.innerHTML = '<span class="text-muted">Checking file...</span>'; }
    try {
        const formData = new FormData();
        formData.append('skillboost_file', file);
        const response = await fetch(_importFetchUrl(cohortApiUrl('/api/import/skillboost/preview')), {
            method: 'POST',
            headers: _importAuthHeaders(),
            credentials: 'same-origin',
            body: formData
        });
        const data = await response.json().catch(function() { return {}; });
        if (!response.ok) {
            if (previewResultEl) { previewResultEl.innerHTML = '<span class="text-danger">' + escapeHtml(data.error || 'Preview failed') + '</span>'; previewResultEl.style.display = 'block'; }
            return;
        }

        const count = data.sheet_count != null ? data.sheet_count : 0;
        const mapping = data.sheet_mapping || [];
        const missing = data.missing_critical_modules || [];
        window.skillboostPreviewState.sheetMapping = mapping;
        window.skillboostPreviewState.missingCritical = missing;

        // Cohort-2 Optional-MCQ-only path keeps its own concise banner.
        if (data.cohort2_optional_import_only && !data.error) {
            var c2m = data.cohort2_optional_mcq_sheet || {};
            var detected = data.detected_sheet_name;
            var rows = data.detected_sheet_rows != null ? data.detected_sheet_rows : 0;
            var htmlC2 = '<strong><i class="fas fa-check-circle text-success"></i> Cohort 2 — Optional MCQ import only</strong><br>' +
                'Required sheet <strong>&quot;' + escapeHtml(detected || c2m.sheet_name || '') + '&quot;</strong> (14.MCQ … Optional) found with <strong>' + (rows || c2m.rows || 0).toLocaleString() + '</strong> row(s).';
            htmlC2 += _renderMissingCriticalBanner(missing);
            htmlC2 += _renderSheetMappingTable(mapping);
            previewResultEl.innerHTML = htmlC2;
        } else if (data.error) {
            var html = '<strong><i class="fas fa-info-circle"></i> ' + count + ' subsheet(s) found.</strong><br>' +
                '<span class="text-warning">' + escapeHtml(data.error) + '</span>';
            html += _renderMissingCriticalBanner(missing);
            html += _renderSheetMappingTable(mapping);
            previewResultEl.innerHTML = html;
        } else {
            var detectedCount = mapping.filter(function(r) { return r && r.status === 'detected'; }).length;
            var unrecognisedCount = mapping.filter(function(r) { return r && r.status === 'unrecognised'; }).length;
            var html = '<strong><i class="fas fa-check-circle text-success"></i> ' + count + ' tab(s) found</strong> ' +
                '(<span style="color:#22c55e;">' + detectedCount + ' detected</span>, ' +
                '<span style="color:#94a3b8;">' + unrecognisedCount + ' ignored</span>).';
            if (data.action_center_profile_sheet_missing) {
                html += '<br><span class="text-muted" style="display:inline-block;margin-top:4px;"><i class="fas fa-info-circle"></i> No Google Skills profile sheet; other recognised subsheets (e.g. Main MCQ) will still import.</span>';
            }
            html += _renderMissingCriticalBanner(missing);
            html += _renderSheetMappingTable(mapping);
            previewResultEl.innerHTML = html;
        }

        previewResultEl.style.display = 'block';

        if (missing && missing.length > 0) {
            window.skillboostPreviewState.requiresConfirmation = true;
            window.skillboostPreviewState.confirmed = false;
            _setSkillboostUploadEnabled(false);
            var cb = document.getElementById('skillboostConfirmMissing');
            if (cb) {
                cb.addEventListener('change', function() {
                    window.skillboostPreviewState.confirmed = !!cb.checked;
                    _setSkillboostUploadEnabled(!!cb.checked);
                });
            }
        } else {
            window.skillboostPreviewState.requiresConfirmation = false;
            window.skillboostPreviewState.confirmed = true;
            _setSkillboostUploadEnabled(true);
        }
    } catch (err) {
        if (previewResultEl) { previewResultEl.innerHTML = '<span class="text-danger">' + escapeHtml(err.message || 'Request failed') + '</span>'; previewResultEl.style.display = 'block'; }
    }
}

// Skill Lab / Skillboost Profile XLSX upload
(function initSkillboostUpload() {
    const zone = document.getElementById('skillboostFileUploadZone');
    const fileInput = document.getElementById('skillboostExcelFile');
    const fileNameDisplay = document.getElementById('skillboostFileNameDisplay');
    if (!zone || !fileInput) return;

    function updateSkillboostZone() {
        const file = fileInput.files[0];
        if (file) {
            zone.classList.add('has-file');
            if (fileNameDisplay) fileNameDisplay.innerHTML = '<i class="fas fa-check-circle"></i> ' + escapeHtml(file.name);
            runSkillboostPreview(file);
        } else {
            zone.classList.remove('has-file');
            if (fileNameDisplay) fileNameDisplay.innerHTML = '';
            const previewResultEl = document.getElementById('skillboostPreviewResult');
            if (previewResultEl) previewResultEl.style.display = 'none';
        }
    }
    fileInput.addEventListener('change', updateSkillboostZone);
    ['dragenter', 'dragover'].forEach(ev => {
        zone.addEventListener(ev, function(e) { e.preventDefault(); e.stopPropagation(); zone.classList.add('drag-over'); });
    });
    ['dragleave', 'drop'].forEach(ev => {
        zone.addEventListener(ev, function(e) { e.preventDefault(); e.stopPropagation(); zone.classList.remove('drag-over'); });
    });
    zone.addEventListener('drop', function(e) {
        const files = e.dataTransfer && e.dataTransfer.files;
        if (files && files.length) { fileInput.files = files; updateSkillboostZone(); }
    });
})();

document.getElementById('skillboostUploadForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const fileInput = document.getElementById('skillboostExcelFile');
    const file = fileInput && fileInput.files[0];
    const errorEl = document.getElementById('skillboostUploadError');
    const successEl = document.getElementById('skillboostUploadSuccess');
    const errorsListEl = document.getElementById('skillboostImportErrors');
    const btn = document.getElementById('skillboostUploadBtn');
    if (errorEl) errorEl.style.display = 'none';
    if (successEl) successEl.style.display = 'none';
    if (errorsListEl) errorsListEl.style.display = 'none';
    var perSheetEl = document.getElementById('skillboostPerSheetErrors');
    if (perSheetEl) { perSheetEl.innerHTML = ''; perSheetEl.style.display = 'none'; }
    if (!file) {
        if (errorEl) { errorEl.textContent = 'Please select an XLSX file'; errorEl.style.display = 'block'; }
        return;
    }
    var preview = window.skillboostPreviewState || {};
    if (preview.requiresConfirmation && !preview.confirmed) {
        if (errorEl) {
            errorEl.textContent = 'Some expected sheets are missing. Tick "Import anyway" in the preview banner to continue.';
            errorEl.style.display = 'block';
        }
        return;
    }
    const formData = new FormData();
    formData.append('skillboost_file', file);
    if (preview.requiresConfirmation && preview.confirmed) {
        formData.append('confirm_missing_modules', 'true');
    }
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Importing (large files may take several minutes)...'; }
    const skillboostImportTimeoutMs = 25 * 60 * 1000;
    const skillboostController = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const skillboostTimeoutId = skillboostController && typeof setTimeout === 'function'
        ? setTimeout(function() { try { skillboostController.abort(); } catch (e) { /* ignore */ } }, skillboostImportTimeoutMs)
        : null;
    try {
        const fetchOpts = {
            method: 'POST',
            headers: _importAuthHeaders(),
            credentials: 'same-origin',
            body: formData
        };
        if (skillboostController) fetchOpts.signal = skillboostController.signal;
        const response = await fetch(_importFetchUrl(cohortApiUrl('/api/import/skillboost')), fetchOpts);
        if (skillboostTimeoutId) clearTimeout(skillboostTimeoutId);
        const data = await response.json().catch(function() { return {}; });
        if (!response.ok) {
            var failMsg = data.error || data.message;
            if (!failMsg) {
                if (response.status === 409) {
                    failMsg = 'Some expected sheets are missing. Tick "Import anyway" in the preview banner, then retry.';
                } else if (response.status === 502 || response.status === 504) {
                    failMsg = 'Gateway timed out (HTTP ' + response.status + '). The import may still have completed on the server — refresh the dashboard and retry only if counts did not change.';
                } else {
                    failMsg = 'Import failed (HTTP ' + response.status + ').';
                }
            }
            if (errorEl) { errorEl.textContent = failMsg; errorEl.style.display = 'block'; }
            return;
        }
        if (errorEl) errorEl.style.display = 'none';
        if (successEl) {
            var msgHtml = '<div><i class="fas fa-check-circle" style="color: #22c55e;"></i> ' +
                escapeHtml(data.message || 'Imported ' + (data.created || 0) + ' created, ' + (data.updated || 0) + ' updated, ' + (data.skipped || 0) + ' skipped.') + '</div>';
            if (data.submission) {
                var sub = data.submission;
                msgHtml += '<div style="margin-top: 8px;"><i class="fas fa-clipboard-check" style="color: #3b82f6;"></i> <strong>Skill Lab Submissions</strong> (sheet: ' + escapeHtml(sub.sheet_name || '') + '): ' +
                    (sub.created || 0) + ' created, ' + (sub.updated || 0) + ' updated, ' + (sub.skipped || 0) + ' skipped.</div>';
            }
            if (data.submission_error) {
                msgHtml += '<div style="margin-top: 8px; color: #ef4444;"><i class="fas fa-exclamation-triangle"></i> Submission import error: ' + escapeHtml(data.submission_error) + '</div>';
            }
            if (data.mcq && data.mcq.length > 0) {
                data.mcq.forEach(function(m) {
                    msgHtml += '<div style="margin-top: 8px;"><i class="fas fa-tasks" style="color: #7c3aed;"></i> <strong>Optional MCQ Track ' + m.track + '</strong> (sheet: ' + escapeHtml(m.sheet_name || '') + '): ' +
                        (m.created || 0) + ' created, ' + (m.updated || 0) + ' updated, ' + (m.skipped || 0) + ' skipped.</div>';
                });
            }
            if (data.mcq_errors && data.mcq_errors.length > 0) {
                data.mcq_errors.forEach(function(e) {
                    msgHtml += '<div style="margin-top: 8px; color: #ef4444;"><i class="fas fa-exclamation-triangle"></i> MCQ Track ' + e.track + ' error: ' + escapeHtml(e.error) + '</div>';
                });
            }
            if (data.main_mcq && data.main_mcq.length > 0) {
                data.main_mcq.forEach(function(m) {
                    msgHtml += '<div style="margin-top: 8px;"><i class="fas fa-clipboard-check" style="color: #059669;"></i> <strong>MCQ Verification Track ' + m.track + '</strong> (sheet: ' + escapeHtml(m.sheet_name || '') + '): ' +
                        (m.created || 0) + ' created, ' + (m.updated || 0) + ' updated, ' + (m.skipped || 0) + ' skipped.</div>';
                });
            }
            if (data.main_mcq_errors && data.main_mcq_errors.length > 0) {
                data.main_mcq_errors.forEach(function(e) {
                    msgHtml += '<div style="margin-top: 8px; color: #ef4444;"><i class="fas fa-exclamation-triangle"></i> Main MCQ Track ' + (e.track != null ? e.track : '?') + ' error: ' + escapeHtml(e.error) + '</div>';
                });
            }
            if (data.lab_completions && data.lab_completions.length > 0) {
                data.lab_completions.forEach(function(lc) {
                    if (lc.error) {
                        msgHtml += '<div style="margin-top: 8px; color: #ef4444;"><i class="fas fa-exclamation-triangle"></i> Lab ' + lc.lab + ' Track ' + lc.track + ' error: ' + escapeHtml(lc.error) + '</div>';
                    } else {
                        msgHtml += '<div style="margin-top: 8px;"><i class="fas fa-code" style="color: #0ea5e9;"></i> <strong>Lab Completion ' + lc.lab + ' Track ' + lc.track + '</strong> (sheet: ' + escapeHtml(lc.sheet_name || '') + '): ' +
                            (lc.created || 0) + ' created, ' + (lc.updated || 0) + ' updated, ' + (lc.skipped || 0) + ' skipped.</div>';
                    }
                });
            }
            if (data.codelab_submission) {
                var cls = data.codelab_submission;
                msgHtml += '<div style="margin-top: 8px;"><i class="fas fa-code" style="color: #0ea5e9;"></i> <strong>Code Lab Submissions</strong> (sheet: ' + escapeHtml(cls.sheet_name || '') + '): ' +
                    (cls.created || 0) + ' created, ' + (cls.updated || 0) + ' updated, ' + (cls.skipped || 0) + ' skipped.</div>';
            }
            if (data.codelab_submission_error) {
                msgHtml += '<div style="margin-top: 8px; color: #ef4444;"><i class="fas fa-exclamation-triangle"></i> Code Lab Submission error: ' + escapeHtml(data.codelab_submission_error) + '</div>';
            }
            if (data.project_submissions && data.project_submissions.length > 0) {
                data.project_submissions.forEach(function(ps) {
                    if (ps.error) {
                        msgHtml += '<div style="margin-top: 8px; color: #ef4444;"><i class="fas fa-exclamation-triangle"></i> Project Track ' + (ps.track != null ? ps.track : '?') + ' error: ' + escapeHtml(ps.error) + '</div>';
                    } else {
                        msgHtml += '<div style="margin-top: 8px;"><i class="fas fa-folder-open" style="color: #7c3aed;"></i> <strong>Project Submission Track ' + (ps.track != null ? ps.track : '?') + '</strong> (sheet: ' + escapeHtml(ps.sheet_name || '') + '): ' +
                            (ps.created || 0) + ' created, ' + (ps.updated || 0) + ' updated, ' + (ps.skipped || 0) + ' skipped.</div>';
                    }
                });
            }
            successEl.innerHTML = msgHtml;
            successEl.style.display = 'block';
        }
        // Combine profile errors, submission errors, and MCQ errors (exclude expected skips)
        var allErrors = (data.errors || []).slice().filter(function(e) {
            return !_isInformationalSkillboostProfileErrorLine(e);
        });
        if (data.submission && data.submission.errors && data.submission.errors.length > 0) {
            allErrors = allErrors.concat(data.submission.errors.map(function(e) { return '[Submission] ' + e; }));
        }
        if (data.mcq && data.mcq.length > 0) {
            data.mcq.forEach(function(m) {
                if (m.errors && m.errors.length > 0) {
                    allErrors = allErrors.concat(m.errors.map(function(e) { return '[MCQ Track ' + m.track + '] ' + e; }));
                }
            });
        }
        if (data.main_mcq && data.main_mcq.length > 0) {
            data.main_mcq.forEach(function(m) {
                if (m.errors && m.errors.length > 0) {
                    allErrors = allErrors.concat(m.errors.map(function(e) { return '[Main MCQ Track ' + m.track + '] ' + e; }));
                }
            });
        }
        if (data.lab_completions && data.lab_completions.length > 0) {
            data.lab_completions.forEach(function(lc) {
                if (lc.errors && lc.errors.length > 0) {
                    allErrors = allErrors.concat(lc.errors.map(function(e) { return '[Lab ' + lc.lab + ' Track ' + lc.track + '] ' + e; }));
                }
            });
        }
        if (data.codelab_submission && data.codelab_submission.errors && data.codelab_submission.errors.length > 0) {
            allErrors = allErrors.concat(data.codelab_submission.errors.map(function(e) { return '[Code Lab Submission] ' + e; }));
        }
        if (data.project_submissions && data.project_submissions.length > 0) {
            data.project_submissions.forEach(function(ps) {
                if (ps.errors && ps.errors.length > 0) {
                    var t = ps.track != null ? ps.track : '?';
                    allErrors = allErrors.concat(ps.errors.map(function(e) { return '[Project Track ' + t + '] ' + e; }));
                }
            });
        }
        if (allErrors.length > 0 && errorsListEl) {
            errorsListEl.innerHTML = '<strong class="text-warning"><i class="fas fa-exclamation-triangle"></i> Import notes / errors (' + allErrors.length + '):</strong><ul class="import-errors-ul">' +
                allErrors.map(function(err) { return '<li>' + escapeHtml(err) + '</li>'; }).join('') + '</ul>';
            errorsListEl.style.display = 'block';
        } else if (errorsListEl) {
            errorsListEl.innerHTML = '';
            errorsListEl.style.display = 'none';
        }
        try { renderPerSheetErrorsPanel(data.per_sheet_errors || []); } catch (e) { /* ignore */ }
        fileInput.value = '';
        const zone = document.getElementById('skillboostFileUploadZone');
        const fileNameDisplay = document.getElementById('skillboostFileNameDisplay');
        if (zone) zone.classList.remove('has-file');
        if (fileNameDisplay) fileNameDisplay.innerHTML = '';
        const previewResultEl = document.getElementById('skillboostPreviewResult');
        if (previewResultEl) previewResultEl.style.display = 'none';
    } catch (err) {
        if (skillboostTimeoutId) clearTimeout(skillboostTimeoutId);
        var msg = err && err.message ? err.message : 'Request failed';
        if (err && err.name === 'AbortError') {
            msg = 'Import timed out after 25 minutes. The server may still be processing; check counts on the dashboard or try importing again (skips already-imported rows where applicable).';
        } else if (msg === 'Failed to fetch' || (typeof TypeError !== 'undefined' && err instanceof TypeError)) {
            msg = 'Connection closed or timed out before the server responded. Large Action Center exports can take many minutes — retry the import, or increase proxy/server timeouts (e.g. nginx proxy_read_timeout).';
        }
        if (errorEl) { errorEl.textContent = msg; errorEl.style.display = 'block'; }
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-upload"></i> Import Skill Lab Profiles'; }
    }
});

// Skill Lab: Verify profiles (streaming progress + final stats)
document.getElementById('skillboostVerifyBtn').addEventListener('click', async function() {
    const btn = document.getElementById('skillboostVerifyBtn');
    const progressEl = document.getElementById('skillboostVerifyProgress');
    const progressBar = document.getElementById('skillboostVerifyProgressBar');
    const progressText = document.getElementById('skillboostVerifyProgressText');
    const statsEl = document.getElementById('skillboostVerifyStats');
    const errorEl = document.getElementById('skillboostVerifyError');
    if (errorEl) errorEl.style.display = 'none';
    if (statsEl) statsEl.style.display = 'none';
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Verifying...'; }
    if (progressEl) { progressEl.style.display = 'block'; progressEl.style.visibility = 'visible'; }
    if (progressBar) progressBar.style.width = '0%';
    if (progressText) progressText.textContent = 'Verifying... 0 / 0';
    try {
        const response = await fetch(_importFetchUrl(cohortApiUrl('/api/import/skillboost/verify?pending_only=1')), {
            method: 'POST',
            headers: _importAuthHeaders(),
            credentials: 'same-origin'
        });
        if (!response.ok) {
            const data = await response.json().catch(function() { return {}; });
            throw new Error(data.error || 'Verification failed');
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let result = null;
        function processChunk(str) {
            const parts = str.split('\n\n');
            for (let i = 0; i < parts.length; i++) {
                const line = parts[i].trim();
                if (!line.startsWith('data:')) continue;
                const payload = line.replace(/^data:\s*/, '').trim();
                if (!payload) continue;
                try {
                    const data = JSON.parse(payload);
                    if (data.done) {
                        result = data;
                        return;
                    }
                    const total = data.total || 0;
                    const current = data.current || 0;
                    const pct = total > 0 ? Math.round((current / total) * 100) : 0;
                    if (progressBar) progressBar.style.width = pct + '%';
                    if (progressText) progressText.textContent = 'Verifying... ' + (current || 0).toLocaleString() + ' / ' + (total || 0).toLocaleString() + ' (Verified: ' + (data.verified_ok || 0) + ', Failed: ' + (data.verified_fail || 0) + ')';
                } catch (e) { /* skip */ }
            }
        }
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const idx = buffer.lastIndexOf('\n\n');
            if (idx !== -1) {
                processChunk(buffer.substring(0, idx + 2));
                buffer = buffer.substring(idx + 2);
            }
            if (result) break;
        }
        if (buffer && !result) processChunk(buffer);
        if (progressEl) progressEl.style.display = 'none';
        if (result && statsEl) {
            const total = result.total || 0;
            const ok = result.verified_ok || 0;
            const fail = result.verified_fail || 0;
            statsEl.innerHTML = '<strong><i class="fas fa-check-circle text-success"></i> Verification complete</strong><br>' +
                '<div style="margin-top: 8px;">' +
                '<span>Total: <strong>' + (total).toLocaleString() + '</strong></span> &nbsp;|&nbsp; ' +
                '<span class="text-success">Verified: <strong>' + (ok).toLocaleString() + '</strong></span> &nbsp;|&nbsp; ' +
                '<span class="text-danger">Failed: <strong>' + (fail).toLocaleString() + '</strong></span>' +
                '</div>';
            statsEl.style.display = 'block';
        }
    } catch (err) {
        if (progressEl) progressEl.style.display = 'none';
        if (errorEl) { errorEl.textContent = err.message || 'Verification failed'; errorEl.style.display = 'block'; }
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-check-circle"></i> Verify profiles'; }
    }
});

// Skill Lab / Code Lab: verify badge submission URLs (SSE + optional min completion date)
var skillboostVerifySubmissionBtn = document.getElementById('skillboostVerifySubmissionBtn');
if (skillboostVerifySubmissionBtn) {
    skillboostVerifySubmissionBtn.addEventListener('click', async function() {
        var btn = document.getElementById('skillboostVerifySubmissionBtn');
        var progressEl = document.getElementById('skillboostVerifySubmissionProgress');
        var progressBar = document.getElementById('skillboostVerifySubmissionProgressBar');
        var progressText = document.getElementById('skillboostVerifySubmissionProgressText');
        var statsEl = document.getElementById('skillboostVerifySubmissionStats');
        var errorEl = document.getElementById('skillboostVerifySubmissionError');
        var minDateEl = document.getElementById('skillboostVerifyMinDate');
        if (errorEl) errorEl.style.display = 'none';
        if (statsEl) statsEl.style.display = 'none';
        var params = ['pending_only=1'];
        var minD = minDateEl && minDateEl.value ? String(minDateEl.value).trim() : '';
        if (minD) params.push('min_date=' + encodeURIComponent(minD));
        var reqUrl = cohortApiUrl('/api/import/submission/verify?' + params.join('&'));
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Verifying...'; }
        if (progressEl) { progressEl.style.display = 'block'; progressEl.style.visibility = 'visible'; }
        if (progressBar) progressBar.style.width = '0%';
        if (progressText) progressText.textContent = 'Verifying submissions... 0 / 0';
        try {
            var response = await fetch(_importFetchUrl(reqUrl), {
                method: 'POST',
                headers: _importAuthHeaders(),
                credentials: 'same-origin'
            });
            if (!response.ok) {
                var errData = await response.json().catch(function() { return {}; });
                throw new Error(errData.error || 'Verification failed');
            }
            var reader = response.body.getReader();
            var decoder = new TextDecoder();
            var buffer = '';
            var result = null;
            function processChunk(str) {
                var parts = str.split('\n\n');
                for (var i = 0; i < parts.length; i++) {
                    var line = parts[i].trim();
                    if (!line.startsWith('data:')) continue;
                    var payload = line.replace(/^data:\s*/, '').trim();
                    if (!payload) continue;
                    try {
                        var data = JSON.parse(payload);
                        if (data.done) {
                            result = data;
                            return;
                        }
                        var total = data.total || 0;
                        var current = data.current || 0;
                        var pct = total > 0 ? Math.round((current / total) * 100) : 0;
                        if (progressBar) progressBar.style.width = pct + '%';
                        var ok = data.verified_ok || 0;
                        var fail = data.verified_fail || 0;
                        var pend = data.pending != null ? data.pending : 0;
                        if (progressText) {
                            progressText.textContent = 'Verifying submissions... ' + (current || 0).toLocaleString() + ' / ' + (total || 0).toLocaleString() +
                                ' (Verified: ' + ok + ', Failed: ' + fail + ', Pending: ' + pend + ')';
                        }
                    } catch (e) { /* skip */ }
                }
            }
            while (true) {
                var readResult = await reader.read();
                if (readResult.done) break;
                buffer += decoder.decode(readResult.value, { stream: true });
                var idx = buffer.lastIndexOf('\n\n');
                if (idx !== -1) {
                    processChunk(buffer.substring(0, idx + 2));
                    buffer = buffer.substring(idx + 2);
                }
                if (result) break;
            }
            if (buffer && !result) processChunk(buffer);
            if (progressEl) progressEl.style.display = 'none';
            if (result && statsEl) {
                var total = result.total || 0;
                var ok = result.verified_ok || 0;
                var fail = result.verified_fail || 0;
                var pend = result.pending != null ? result.pending : 0;
                statsEl.innerHTML = '<strong><i class="fas fa-check-circle text-success"></i> Submission verification complete</strong><br>' +
                    '<div style="margin-top: 8px;">' +
                    '<span>Total: <strong>' + total.toLocaleString() + '</strong></span> &nbsp;|&nbsp; ' +
                    '<span class="text-success">Verified: <strong>' + ok.toLocaleString() + '</strong></span> &nbsp;|&nbsp; ' +
                    '<span class="text-danger">Failed: <strong>' + fail.toLocaleString() + '</strong></span> &nbsp;|&nbsp; ' +
                    '<span style="color:#38bdf8;">Pending: <strong>' + pend.toLocaleString() + '</strong></span>' +
                    '</div>';
                statsEl.style.display = 'block';
            }
        } catch (err) {
            if (progressEl) progressEl.style.display = 'none';
            if (errorEl) { errorEl.textContent = err.message || 'Verification failed'; errorEl.style.display = 'block'; }
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-award"></i> Verify Submission'; }
        }
    });
}
