"""
Data import routes
"""
import os
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from server.models import db, BobCompany
from server.utils.auth import get_current_user
from server.utils.permissions import require_role, require_page_access
from server.utils.excel_parser import (
    parse_excel,
    get_db_fields,
    auto_map_fields,
    import_data
)
from server.utils.bob_match import recalculate_bob_match, _normalize

bp = Blueprint('import', __name__)

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.route('/preview', methods=['POST'])
@require_page_access('import')
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
@require_page_access('import')
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
        
        # Optional: set additional_info for master_logs (source, filename)
        try:
            from server.utils.audit import set_audit_extra
            set_audit_extra({"source": "csv_import", "filename": filename})
        except Exception:
            pass
        
        # Execute import
        result = import_data(df, mappings, mode)
        
        # Recalculate BOB match for all UserPII so new/updated users get bob_match set
        try:
            recalculate_bob_match()
        except Exception:
            pass
        
        # Clean up temp file
        try:
            os.remove(file_path)
        except:
            pass
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


BOB_INSERT_BATCH = 5000


@bp.route('/bob', methods=['POST'])
@require_page_access('import')
def import_bob_companies():
    """Import Book of Business company names from XLSX. Replaces existing list and recalculates bob_match for all UserPII."""
    try:
        if 'file' not in request.files and 'bob_file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files.get('file') or request.files.get('bob_file')
        if not file or file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only Excel files (.xlsx, .xls) are allowed for BOB import'}), 400

        upload_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, secure_filename(file.filename))
        file.save(file_path)

        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            ws = wb.active
            company_names = []
            for row in ws.iter_rows(min_row=1, max_col=1, values_only=True):
                val = row[0]
                if val is not None and str(val).strip():
                    company_names.append(str(val).strip())
            wb.close()
        except Exception as e:
            try:
                os.remove(file_path)
            except Exception:
                pass
            return jsonify({'error': f'Error reading XLSX: {str(e)}'}), 400

        try:
            os.remove(file_path)
        except Exception:
            pass

        # Replace bob_companies: delete all then batch insert
        db.session.query(BobCompany).delete()
        db.session.commit()

        for i in range(0, len(company_names), BOB_INSERT_BATCH):
            batch = company_names[i:i + BOB_INSERT_BATCH]
            for name in batch:
                norm = _normalize(name)
                db.session.add(BobCompany(company_name=name, normalized_name=norm if norm else None))
            db.session.commit()

        updated = recalculate_bob_match()

        return jsonify({
            'companies_imported': len(company_names),
            'bob_match_updated': updated,
            'message': f'Imported {len(company_names)} companies and updated BOB match for {updated} profile(s).'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
