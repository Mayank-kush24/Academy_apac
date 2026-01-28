"""
Data import routes
"""
import os
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from server.models import db
from server.utils.auth import get_current_user
from server.utils.permissions import require_role
from server.utils.excel_parser import (
    parse_excel,
    get_db_fields,
    auto_map_fields,
    import_data
)

bp = Blueprint('import', __name__)

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.route('/preview', methods=['POST'])
@require_role('editor', 'admin')
def preview_import():
    """Preview Excel file and return column mappings"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Only Excel files (.xlsx, .xls) are allowed'}), 400
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        upload_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        # Parse Excel
        df = parse_excel(file_path)
        
        # Get Excel columns
        excel_columns = list(df.columns)
        
        # Auto-map fields
        auto_mappings = auto_map_fields(excel_columns)
        
        # Get first 5 rows as preview
        preview_rows = df.head(5).fillna('').to_dict('records')
        
        # Get DB fields for dropdown
        db_fields = get_db_fields()
        
        # Clean up temp file
        try:
            os.remove(file_path)
        except:
            pass
        
        return jsonify({
            'excel_columns': excel_columns,
            'preview_rows': preview_rows,
            'auto_mappings': auto_mappings,
            'db_fields': db_fields
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/execute', methods=['POST'])
@require_role('editor', 'admin')
def execute_import():
    """Execute data import with field mappings"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type'}), 400
        
        # Get mappings and mode from form data
        mappings_json = request.form.get('mappings')
        mode = request.form.get('mode', 'create')
        
        if not mappings_json:
            return jsonify({'error': 'Field mappings are required'}), 400
        
        import json
        mappings = json.loads(mappings_json)
        
        if mode not in ['create', 'create_update', 'update_only']:
            return jsonify({'error': 'Invalid import mode'}), 400
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        upload_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        # Parse Excel
        df = parse_excel(file_path)
        
        # Execute import
        result = import_data(df, mappings, mode)
        
        # Clean up temp file
        try:
            os.remove(file_path)
        except:
            pass
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
