"""
Data import routes
"""
import os
import json
import queue
import threading
from flask import Blueprint, request, jsonify, Response, stream_with_context, current_app
from werkzeug.utils import secure_filename
from server.models import db, BobCompany, SkillboostProfile
from server.utils.auth import get_current_user
from server.utils.permissions import require_role, require_page_access
from server.utils.excel_parser import (
    parse_excel,
    parse_excel_sheet,
    get_db_fields,
    auto_map_fields,
    import_data,
    find_sheet_by_substring,
    get_skillboost_preview,
    _find_email_column,
    _find_profile_link_column,
    import_skillboost_profile,
    SKILLBOOST_SHEET_SUBSTRING,
)
from server.utils.bob_match import recalculate_bob_match, _normalize
from server.utils.cache import clear_cache
from server.utils.skillboost_verify import verify_profile_url
from server.utils.audit import set_audit_session_vars
from datetime import datetime

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
        
        # Streaming: return SSE so frontend can show live progress
        if request.args.get('stream') == '1':
            progress_queue = queue.Queue()
            app = current_app._get_current_object()

            def progress_callback(created, updated, skipped):
                progress_queue.put({'created': created, 'updated': updated, 'skipped': skipped})

            def run_import():
                with app.app_context():
                    try:
                        res = import_data(df, mappings, mode, progress_callback=progress_callback)
                        try:
                            recalculate_bob_match()
                        except Exception:
                            pass
                        try:
                            clear_cache('_get_dashboard_data_cached')
                        except Exception:
                            pass
                        progress_queue.put({'done': True, 'result': res})
                    except Exception as e:
                        progress_queue.put({'done': True, 'error': str(e)})
                    finally:
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass

            thread = threading.Thread(target=run_import)
            thread.start()

            def generate():
                while True:
                    try:
                        item = progress_queue.get(timeout=0.5)
                    except queue.Empty:
                        yield "data: {}\n\n"
                        continue
                    if item.get('done'):
                        if 'error' in item:
                            yield "data: " + json.dumps({'error': item['error']}) + "\n\n"
                        else:
                            yield "data: " + json.dumps(item.get('result', {})) + "\n\n"
                        break
                    yield "data: " + json.dumps(item) + "\n\n"
                thread.join()

            return Response(
                stream_with_context(generate()),
                mimetype='text/event-stream',
                headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'}
            )

        # Non-streaming: execute import and return JSON
        result = import_data(df, mappings, mode)
        try:
            recalculate_bob_match()
        except Exception:
            pass
        try:
            clear_cache('_get_dashboard_data_cached')
        except Exception:
            pass
        try:
            os.remove(file_path)
        except Exception:
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

        try:
            clear_cache('_get_dashboard_data_cached')
        except Exception:
            pass

        return jsonify({
            'companies_imported': len(company_names),
            'bob_match_updated': updated,
            'message': f'Imported {len(company_names)} companies and updated BOB match for {updated} profile(s).'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/skillboost/preview', methods=['POST'])
@require_page_access('import')
def preview_skillboost_file():
    """
    Preview Skill Lab XLSX: return sheet count, sheet names, detected sheet name and row count.
    Does not perform import.
    """
    try:
        if 'file' not in request.files and 'skillboost_file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files.get('file') or request.files.get('skillboost_file')
        if not file or file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only Excel files (.xlsx, .xls) are allowed'}), 400

        upload_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, secure_filename(file.filename))
        file.save(file_path)
        try:
            preview = get_skillboost_preview(file_path)
            return jsonify(preview), 200
        finally:
            try:
                os.remove(file_path)
            except Exception:
                pass
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/skillboost', methods=['POST'])
@require_page_access('import')
def import_skillboost_profiles():
    """
    Import Skill Lab / Google Skills Boost profiles from XLSX.
    Auto-detects sheet whose name contains "Share your Google Skills Pu" (case-insensitive).
    Maps Email -> email, and a column containing profile/link/skills -> google_cloud_skills_boost_profile_link.
    Uses skillboost_profile table; does not overwrite rows where valid = TRUE.
    """
    try:
        if 'file' not in request.files and 'skillboost_file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files.get('file') or request.files.get('skillboost_file')
        if not file or file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only Excel files (.xlsx, .xls) are allowed for Skill Lab profile import'}), 400

        upload_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, secure_filename(file.filename))
        file.save(file_path)

        sheet_name = find_sheet_by_substring(file_path, SKILLBOOST_SHEET_SUBSTRING)
        if not sheet_name:
            try:
                os.remove(file_path)
            except Exception:
                pass
            return jsonify({
                'error': f'No worksheet found whose name contains "{SKILLBOOST_SHEET_SUBSTRING}". '
                         'Please use an XLSX file that has a sheet with that name (e.g. from Google Skills Boost / Skill Lab export).'
            }), 400

        df = parse_excel_sheet(file_path, sheet_name)
        if df is None or len(df) == 0:
            try:
                os.remove(file_path)
            except Exception:
                pass
            return jsonify({'error': 'The selected sheet is empty'}), 400

        columns = list(df.columns)
        email_col = _find_email_column(columns)
        profile_link_col = _find_profile_link_column(columns)
        if not email_col:
            try:
                os.remove(file_path)
            except Exception:
                pass
            return jsonify({'error': 'Could not find an Email column in the sheet. Please ensure the sheet has a column named "Email".'}), 400
        if not profile_link_col:
            try:
                os.remove(file_path)
            except Exception:
                pass
            return jsonify({
                'error': 'Could not find a profile link column (column containing "profile", "link", or "skills"). '
                         'Please ensure the sheet has a column for the Google Skills Boost public profile link.'
            }), 400

        try:
            from server.utils.audit import set_audit_extra
            set_audit_extra({"source": "skillboost_import", "filename": file.filename, "sheet": sheet_name})
        except Exception:
            pass

        result = import_skillboost_profile(df, email_col, profile_link_col)
        try:
            clear_cache('_get_dashboard_data_cached')
        except Exception:
            pass
        try:
            os.remove(file_path)
        except Exception:
            pass

        return jsonify({
            'total_rows': result['total_rows'],
            'created': result['created'],
            'updated': result['updated'],
            'skipped': result['skipped'],
            'errors': result.get('errors', []),
            'message': f"Imported Skill Lab profiles: {result['created']} created, {result['updated']} updated, {result['skipped']} skipped."
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _verify_one(email, link):
    """Worker: verify a single URL; returns (email, link, valid, remarks)."""
    valid, remarks = verify_profile_url(link)
    return (email, link, valid, remarks)


def _verify_skillboost_stream(pending_only=False):
    """Generator that verifies SkillboostProfile rows in parallel and yields SSE progress events.
    Uses ThreadPoolExecutor (same idea as verify_skillboost_profile_csv.py --workers) for speed.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    query = SkillboostProfile.query
    if pending_only:
        query = query.filter(SkillboostProfile.valid == False)
    rows = query.all()
    total = len(rows)
    if total == 0:
        yield f"data: {json.dumps({'done': True, 'total': 0, 'verified_ok': 0, 'verified_fail': 0})}\n\n"
        return
    rec_map = {(r.email, r.google_cloud_skills_boost_profile_link or ''): r for r in rows}
    workers = min(10, total)
    verified_ok = 0
    verified_fail = 0
    current = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_verify_one, rec.email, rec.google_cloud_skills_boost_profile_link or ''): (rec.email, rec.google_cloud_skills_boost_profile_link or '')
            for rec in rows
        }
        for future in as_completed(futures):
            try:
                email, link, valid, remarks = future.result()
            except Exception:
                email, link = futures[future]
                valid, remarks = False, 'Request Failed'
            rec = rec_map.get((email, link))
            if rec:
                try:
                    rec.valid = valid
                    rec.remarks = remarks
                    rec.updated_at = datetime.utcnow()
                    set_audit_session_vars()  # so master_logs trigger sees current user (transaction-local)
                    db.session.commit()
                    if valid:
                        verified_ok += 1
                    else:
                        verified_fail += 1
                except Exception:
                    db.session.rollback()
            current += 1
            yield f"data: {json.dumps({'current': current, 'total': total, 'verified_ok': verified_ok, 'verified_fail': verified_fail})}\n\n"
    yield f"data: {json.dumps({'done': True, 'total': total, 'verified_ok': verified_ok, 'verified_fail': verified_fail})}\n\n"
    # Auto-allocate credit links to newly verified profiles (and any unallocated)
    try:
        from server.routes.skilllab import run_credit_allocation
        run_credit_allocation()
    except Exception:
        pass
    try:
        clear_cache('_get_dashboard_data_cached')
    except Exception:
        pass


@bp.route('/skillboost/verify', methods=['POST', 'GET'])
@require_page_access('import')
def verify_skillboost_profiles():
    """
    Verify Skill Lab / Skillboost profile URLs. Streams progress via SSE.
    Query: ?pending_only=1 to only verify rows where valid = FALSE.
    """
    pending_only = request.args.get('pending_only', '0') == '1'
    return Response(
        stream_with_context(_verify_skillboost_stream(pending_only=pending_only)),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'},
    )
