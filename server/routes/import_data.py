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
    load_all_skillboost_sheets,
    _find_email_column,
    _find_profile_link_column,
    import_skillboost_profile,
    import_skilllab_submission,
    import_codelab_submission,
    import_project_submission,
    import_lab_completion_sheet,
    import_main_mcq_response,
    SKILLBOOST_SHEET_SUBSTRING,
    SKILLLAB_SUBMISSION_SHEET_SUBSTRING,
    CODELAB_SUBMISSION_SHEET_SUBSTRING,
    LAB_COMPLETION_SHEET_SUBSTRINGS,
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
    file_path = None
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

        # Open workbook once and load all sheets needed for import (avoids many file reads)
        sheets = load_all_skillboost_sheets(file_path)
        if not sheets.get('profile_sheet_name') or sheets.get('profile_df') is None:
            return jsonify({
                'error': f'No worksheet found whose name contains "{SKILLBOOST_SHEET_SUBSTRING}". '
                         'Please use an XLSX file that has a sheet with that name (e.g. from Google Skills Boost / Skill Lab export).'
            }), 400

        df = sheets['profile_df']
        if len(df) == 0:
            return jsonify({'error': 'The selected sheet is empty'}), 400

        sheet_name = sheets['profile_sheet_name']
        columns = list(df.columns)
        email_col = _find_email_column(columns)
        profile_link_col = _find_profile_link_column(columns)
        if not email_col:
            return jsonify({'error': 'Could not find an Email column in the sheet. Please ensure the sheet has a column named "Email".'}), 400
        if not profile_link_col:
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

        # Skill Lab Submission (already loaded)
        submission_result = None
        submission_sheet = sheets.get('submission_sheet_name')
        sub_df = sheets.get('submission_df')
        if submission_sheet and sub_df is not None and len(sub_df) > 0:
            try:
                from server.utils.audit import set_audit_extra
                set_audit_extra({"source": "skilllab_submission_import", "filename": file.filename, "sheet": submission_sheet})
            except Exception:
                pass
            try:
                submission_result = import_skilllab_submission(sub_df)
            except Exception as sub_err:
                submission_result = {'error': str(sub_err)}

        # Code Lab Submission (already loaded)
        codelab_result = None
        codelab_sheet = sheets.get('codelab_sheet_name')
        codelab_df = sheets.get('codelab_df')
        if codelab_sheet and codelab_df is not None and len(codelab_df) > 0:
            try:
                from server.utils.audit import set_audit_extra
                set_audit_extra({"source": "codelab_submission_import", "filename": file.filename, "sheet": codelab_sheet})
            except Exception:
                pass
            try:
                codelab_result = import_codelab_submission(codelab_df)
            except Exception as codelab_err:
                codelab_result = {'error': str(codelab_err)}

        # Lab Completion sheets (already loaded)
        lab_completion_results = []
        for lc in sheets.get('lab_completion_sheets', []):
            try:
                lc_df = lc.get('df')
                if lc_df is not None and len(lc_df) > 0:
                    try:
                        from server.utils.audit import set_audit_extra
                        set_audit_extra({"source": "lab_completion_import", "filename": file.filename, "sheet": lc['sheet_name']})
                    except Exception:
                        pass
                    lc_result = import_lab_completion_sheet(lc_df, track_number=lc['track'], lab_number=lc['lab'])
                    lc_result['sheet_name'] = lc['sheet_name']
                    lc_result['lab'] = lc['lab']
                    lc_result['track'] = lc['track']
                    lab_completion_results.append(lc_result)
            except Exception as lc_err:
                lab_completion_results.append({
                    'error': str(lc_err),
                    'sheet_name': lc.get('sheet_name', ''),
                    'lab': lc.get('lab'),
                    'track': lc.get('track'),
                })

        # Main MCQ sheets (already loaded)
        main_mcq_results = []
        main_mcq_errors = []
        for sheet_info in sheets.get('main_mcq_sheets', []):
            track = sheet_info.get('track')
            main_sheet_name = sheet_info.get('sheet_name')
            main_df = sheet_info.get('df')
            try:
                if main_df is not None and len(main_df) > 0:
                    from server.utils.audit import set_audit_extra
                    set_audit_extra({"source": "main_mcq_import", "filename": file.filename, "sheet": main_sheet_name})
                    mcr = import_main_mcq_response(main_df, track)
                    mcr['track'] = track
                    mcr['sheet_name'] = main_sheet_name
                    main_mcq_results.append(mcr)
                else:
                    main_mcq_errors.append({'track': track, 'sheet_name': main_sheet_name, 'error': 'Sheet empty'})
            except Exception as main_err:
                main_mcq_errors.append({'track': track, 'sheet_name': main_sheet_name, 'error': str(main_err)})

        try:
            clear_cache('_get_dashboard_data_cached')
        except Exception:
            pass
        if submission_result and 'error' not in submission_result:
            try:
                clear_cache('_get_skilllab_submission_stats_cached')
            except Exception:
                pass
        if codelab_result and 'error' not in codelab_result:
            try:
                clear_cache('_get_codelab_submission_stats_cached')
            except Exception:
                pass

        project_submission_results = []
        for ps in sheets.get('project_submission_sheets', []):
            ps_df = ps.get('df')
            if ps_df is None or len(ps_df) == 0:
                continue
            try:
                from server.utils.audit import set_audit_extra
                set_audit_extra({
                    "source": "project_submission_import",
                    "filename": file.filename,
                    "sheet": ps.get('sheet_name'),
                    "track": ps.get('track'),
                })
            except Exception:
                pass
            try:
                ps_result = import_project_submission(ps_df, track_number=ps['track'])
                ps_result['sheet_name'] = ps.get('sheet_name')
                ps_result['track'] = ps.get('track')
                project_submission_results.append(ps_result)
            except Exception as ps_err:
                project_submission_results.append({
                    'error': str(ps_err),
                    'sheet_name': ps.get('sheet_name', ''),
                    'track': ps.get('track'),
                })

        if project_submission_results:
            try:
                clear_cache('_get_project_submission_stats_cached')
            except Exception:
                pass

        if lab_completion_results:
            try:
                clear_cache('_get_codelab_submission_stats_cached')
            except Exception:
                pass

        response = {
            'total_rows': result['total_rows'],
            'created': result['created'],
            'updated': result['updated'],
            'skipped': result['skipped'],
            'errors': result.get('errors', []),
            'message': f"Imported Skill Lab profiles: {result['created']} created, {result['updated']} updated, {result['skipped']} skipped."
        }

        if submission_result:
            if 'error' in submission_result:
                response['submission_error'] = submission_result['error']
            else:
                response['submission'] = {
                    'total_rows': submission_result['total_rows'],
                    'created': submission_result['created'],
                    'updated': submission_result['updated'],
                    'skipped': submission_result['skipped'],
                    'errors': submission_result.get('errors', []),
                    'sheet_name': submission_sheet,
                }
                response['message'] += (
                    f" | Skill Lab Submissions: {submission_result['created']} created, "
                    f"{submission_result['updated']} updated, {submission_result['skipped']} skipped."
                )

        if codelab_result:
            if 'error' in codelab_result:
                response['codelab_submission_error'] = codelab_result['error']
            else:
                response['codelab_submission'] = {
                    'total_rows': codelab_result['total_rows'],
                    'created': codelab_result['created'],
                    'updated': codelab_result['updated'],
                    'skipped': codelab_result['skipped'],
                    'errors': codelab_result.get('errors', []),
                    'sheet_name': codelab_sheet,
                }
                response['message'] += (
                    f" | Code Lab Submissions: {codelab_result['created']} created, "
                    f"{codelab_result['updated']} updated, {codelab_result['skipped']} skipped."
                )

        if project_submission_results:
            response['project_submissions'] = []
            for psr in project_submission_results:
                if 'error' in psr:
                    response['project_submissions'].append({
                        'sheet_name': psr.get('sheet_name', ''),
                        'track': psr.get('track'),
                        'error': psr['error'],
                    })
                    err_snip = str(psr.get('error', ''))[:120]
                    response['message'] += f" | Project Track {psr.get('track', '?')} error: {err_snip}"
                else:
                    response['project_submissions'].append({
                        'sheet_name': psr.get('sheet_name', ''),
                        'track': psr.get('track'),
                        'total_rows': psr['total_rows'],
                        'created': psr['created'],
                        'updated': psr['updated'],
                        'skipped': psr['skipped'],
                        'errors': psr.get('errors', []),
                    })
                    response['message'] += (
                        f" | Project Track {psr.get('track')}: {psr['created']} created, "
                        f"{psr['updated']} updated, {psr['skipped']} skipped."
                    )

        if lab_completion_results:
            response['lab_completions'] = []
            for lcr in lab_completion_results:
                if 'error' in lcr:
                    response['lab_completions'].append({
                        'sheet_name': lcr.get('sheet_name', ''),
                        'lab': lcr.get('lab'),
                        'track': lcr.get('track'),
                        'error': lcr['error'],
                    })
                else:
                    response['lab_completions'].append({
                        'sheet_name': lcr.get('sheet_name', ''),
                        'lab': lcr.get('lab'),
                        'track': lcr.get('track'),
                        'total_rows': lcr['total_rows'],
                        'created': lcr['created'],
                        'updated': lcr['updated'],
                        'skipped': lcr['skipped'],
                        'errors': lcr.get('errors', []),
                    })
                    response['message'] += (
                        f" | Lab {lcr['lab']} Track {lcr['track']}: {lcr['created']} created, "
                        f"{lcr['updated']} updated, {lcr['skipped']} skipped."
                    )

        if main_mcq_results:
            response['main_mcq'] = []
            for mcr in main_mcq_results:
                response['main_mcq'].append({
                    'track': mcr['track'],
                    'sheet_name': mcr.get('sheet_name', ''),
                    'total_rows': mcr['total_rows'],
                    'created': mcr['created'],
                    'updated': mcr['updated'],
                    'skipped': mcr['skipped'],
                    'errors': mcr.get('errors', []),
                })
                response['message'] += (
                    f" | Main MCQ Track {mcr['track']}: {mcr['created']} created, "
                    f"{mcr['updated']} updated, {mcr['skipped']} skipped."
                )
        if main_mcq_errors:
            response['main_mcq_errors'] = main_mcq_errors

        return jsonify(response), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if file_path:
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception:
                pass


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
