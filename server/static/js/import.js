/**
 * Import Data JavaScript
 */

let currentStep = 1;
let excelData = null;
let fieldMappings = {};

// Premium file upload zone: show selected file and support drag-and-drop
(function initFileUploadZone() {
    const zone = document.getElementById('fileUploadZone');
    const fileInput = document.getElementById('excelFile');
    const fileNameDisplay = document.getElementById('fileNameDisplay');

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
document.getElementById('uploadForm').addEventListener('submit', async function(e) {
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
        const token = getAuthToken();
        if (!token) {
            throw new Error('Not authenticated');
        }
        
        const response = await fetch('/api/import/preview', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
                // Don't set Content-Type, let browser set it with boundary for FormData
            },
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

    const token = getAuthToken();
    if (!token) {
        alert('Not authenticated');
        return;
    }

    showImportProgressOverlay();

    try {
        const response = await fetch('/api/import/execute?stream=1', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token },
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
                        setImportProgressStats(data.created || 0, data.updated || 0, data.skipped || 0);
                    } else if (data.created !== undefined || data.updated !== undefined || data.skipped !== undefined) {
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
                    if (data.total_rows !== undefined && data.created !== undefined) result = data;
                    else if (data.created !== undefined) setImportProgressStats(data.created || 0, data.updated || 0, data.skipped || 0);
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

// Book of Business (BOB) XLSX upload
(function initBobUpload() {
    const zone = document.getElementById('bobFileUploadZone');
    const fileInput = document.getElementById('bobExcelFile');
    const fileNameDisplay = document.getElementById('bobFileNameDisplay');
    if (!zone || !fileInput) return;

    function updateBobZone() {
        const file = fileInput.files[0];
        if (file) {
            zone.classList.add('has-file');
            if (fileNameDisplay) fileNameDisplay.innerHTML = '<i class="fas fa-check-circle"></i> ' + escapeHtml(file.name);
        } else {
            zone.classList.remove('has-file');
            if (fileNameDisplay) fileNameDisplay.innerHTML = '';
        }
    }
    fileInput.addEventListener('change', updateBobZone);
    ['dragenter', 'dragover'].forEach(ev => {
        zone.addEventListener(ev, function(e) { e.preventDefault(); e.stopPropagation(); zone.classList.add('drag-over'); });
    });
    ['dragleave', 'drop'].forEach(ev => {
        zone.addEventListener(ev, function(e) { e.preventDefault(); e.stopPropagation(); zone.classList.remove('drag-over'); });
    });
    zone.addEventListener('drop', function(e) {
        const files = e.dataTransfer && e.dataTransfer.files;
        if (files && files.length) { fileInput.files = files; updateBobZone(); }
    });
})();

document.getElementById('bobUploadForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const fileInput = document.getElementById('bobExcelFile');
    const file = fileInput && fileInput.files[0];
    const errorEl = document.getElementById('bobUploadError');
    const successEl = document.getElementById('bobUploadSuccess');
    const btn = document.getElementById('bobUploadBtn');
    if (errorEl) errorEl.style.display = 'none';
    if (successEl) successEl.style.display = 'none';
    if (!file) {
        if (errorEl) { errorEl.textContent = 'Please select an XLSX file'; errorEl.style.display = 'block'; }
        return;
    }
    const formData = new FormData();
    formData.append('bob_file', file);
    const token = typeof getAuthToken === 'function' ? getAuthToken() : localStorage.getItem('token');
    if (!token) {
        if (errorEl) { errorEl.textContent = 'Not authenticated'; errorEl.style.display = 'block'; }
        return;
    }
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Importing...'; }
    try {
        const response = await fetch('/api/import/bob', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token },
            body: formData
        });
        const data = await response.json().catch(function() { return {}; });
        if (!response.ok) {
            if (errorEl) { errorEl.textContent = data.error || 'Import failed'; errorEl.style.display = 'block'; }
            return;
        }
        if (successEl) {
            successEl.innerHTML = (data.message || 'Imported ' + (data.companies_imported || 0) + ' companies. BOB match updated for ' + (data.bob_match_updated || 0) + ' profile(s).');
            successEl.style.display = 'block';
        }
        fileInput.value = '';
        const zone = document.getElementById('bobFileUploadZone');
        const fileNameDisplay = document.getElementById('bobFileNameDisplay');
        if (zone) zone.classList.remove('has-file');
        if (fileNameDisplay) fileNameDisplay.innerHTML = '';
    } catch (err) {
        if (errorEl) { errorEl.textContent = err.message || 'Request failed'; errorEl.style.display = 'block'; }
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-upload"></i> Import Book of Business'; }
    }
});

// Skill Lab: run preview and show subsheet/sheet/row info (called automatically when file is selected)
async function runSkillboostPreview(file) {
    const previewResultEl = document.getElementById('skillboostPreviewResult');
    const errorEl = document.getElementById('skillboostUploadError');
    if (!file) {
        if (previewResultEl) previewResultEl.style.display = 'none';
        return;
    }
    if (errorEl) errorEl.style.display = 'none';
    const token = typeof getAuthToken === 'function' ? getAuthToken() : localStorage.getItem('token');
    if (!token) {
        if (errorEl) { errorEl.textContent = 'Not authenticated'; errorEl.style.display = 'block'; }
        return;
    }
    if (previewResultEl) { previewResultEl.style.display = 'block'; previewResultEl.innerHTML = '<span class="text-muted">Checking file...</span>'; }
    try {
        const formData = new FormData();
        formData.append('skillboost_file', file);
        const response = await fetch('/api/import/skillboost/preview', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token },
            body: formData
        });
        const data = await response.json().catch(function() { return {}; });
        if (!response.ok) {
            if (previewResultEl) { previewResultEl.innerHTML = '<span class="text-danger">' + escapeHtml(data.error || 'Preview failed') + '</span>'; previewResultEl.style.display = 'block'; }
            return;
        }
        const count = data.sheet_count != null ? data.sheet_count : 0;
        const names = data.sheet_names || [];
        const detected = data.detected_sheet_name;
        const rows = data.detected_sheet_rows != null ? data.detected_sheet_rows : 0;
        if (data.error) {
            previewResultEl.innerHTML = '<strong><i class="fas fa-info-circle"></i> ' + count + ' subsheet(s) detected.</strong><br>' +
                '<span class="text-warning">' + escapeHtml(data.error) + '</span>' +
                (names.length ? '<br><span class="text-muted">Sheet names: ' + escapeHtml(names.join(', ')) + '</span>' : '');
        } else {
            previewResultEl.innerHTML = '<strong><i class="fas fa-check-circle text-success"></i> ' + count + ' subsheet(s) detected.</strong><br>' +
                'Sheet <strong>&quot;' + escapeHtml(detected || '') + '&quot;</strong> (Share your Google Skills Pu) detected with <strong>' + (rows || 0).toLocaleString() + '</strong> row(s).';
        }
        previewResultEl.style.display = 'block';
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
    if (!file) {
        if (errorEl) { errorEl.textContent = 'Please select an XLSX file'; errorEl.style.display = 'block'; }
        return;
    }
    const formData = new FormData();
    formData.append('skillboost_file', file);
    const token = typeof getAuthToken === 'function' ? getAuthToken() : localStorage.getItem('token');
    if (!token) {
        if (errorEl) { errorEl.textContent = 'Not authenticated'; errorEl.style.display = 'block'; }
        return;
    }
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Importing...'; }
    try {
        const response = await fetch('/api/import/skillboost', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token },
            body: formData
        });
        const data = await response.json().catch(function() { return {}; });
        if (!response.ok) {
            if (errorEl) { errorEl.textContent = data.error || 'Import failed'; errorEl.style.display = 'block'; }
            return;
        }
        if (successEl) {
            successEl.innerHTML = (data.message || 'Imported ' + (data.created || 0) + ' created, ' + (data.updated || 0) + ' updated, ' + (data.skipped || 0) + ' skipped.');
            successEl.style.display = 'block';
        }
        if (data.errors && data.errors.length > 0 && errorsListEl) {
            errorsListEl.innerHTML = '<strong class="text-warning"><i class="fas fa-exclamation-triangle"></i> Import notes / errors (' + data.errors.length + '):</strong><ul class="import-errors-ul">' +
                data.errors.map(function(err) { return '<li>' + escapeHtml(err) + '</li>'; }).join('') + '</ul>';
            errorsListEl.style.display = 'block';
        } else if (errorsListEl) {
            errorsListEl.innerHTML = '';
            errorsListEl.style.display = 'none';
        }
        fileInput.value = '';
        const zone = document.getElementById('skillboostFileUploadZone');
        const fileNameDisplay = document.getElementById('skillboostFileNameDisplay');
        if (zone) zone.classList.remove('has-file');
        if (fileNameDisplay) fileNameDisplay.innerHTML = '';
        const previewResultEl = document.getElementById('skillboostPreviewResult');
        if (previewResultEl) previewResultEl.style.display = 'none';
    } catch (err) {
        if (errorEl) { errorEl.textContent = err.message || 'Request failed'; errorEl.style.display = 'block'; }
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
    const token = typeof getAuthToken === 'function' ? getAuthToken() : localStorage.getItem('token');
    if (!token) {
        if (errorEl) { errorEl.textContent = 'Not authenticated'; errorEl.style.display = 'block'; }
        return;
    }
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Verifying...'; }
    if (progressEl) { progressEl.style.display = 'block'; progressEl.style.visibility = 'visible'; }
    if (progressBar) progressBar.style.width = '0%';
    if (progressText) progressText.textContent = 'Verifying... 0 / 0';
    try {
        const response = await fetch('/api/import/skillboost/verify', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token }
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
