/**
 * Import Data JavaScript
 */

let currentStep = 1;
let excelData = null;
let fieldMappings = {};

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
}

/**
 * Execute import
 */
async function executeImport() {
    const mode = document.querySelector('input[name="importMode"]:checked').value;
    
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
