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
 * Execute import
 */
async function executeImport() {
    // Get mode from selected option or radio button
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
    
    // Get the file again (we need to re-upload it)
    const fileInput = document.getElementById('excelFile');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('File is required');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mappings', JSON.stringify(fieldMappings));
    formData.append('mode', mode);
    
    try {
        const token = getAuthToken();
        if (!token) {
            throw new Error('Not authenticated');
        }
        
        const response = await fetch('/api/import/execute', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
                // Don't set Content-Type, let browser set it with boundary for FormData
            },
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Import failed');
        }
        
        const result = await response.json();
        displayResults(result);
        goToStep(4);
        
    } catch (error) {
        alert('Import failed: ' + error.message);
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
