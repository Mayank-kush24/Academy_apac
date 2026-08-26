"""
Data import routes
"""
import os
import json
import queue
import threading
from flask import Blueprint, request, jsonify, Response, stream_with_context, current_app, g
from werkzeug.utils import secure_filename
from server.models import db, BobCompany, SkillboostProfile, SkillLabSubmission, CodeLabSubmission
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
    import_codelab_submission_sheets,
    import_project_submission,
    import_lab_completion_sheet,
    import_main_mcq_response,
    import_optional_mcq_response,
    skillboost_sheet_not_found_message,
    action_center_has_non_profile_imports,
    cohort2_action_center_optional_mcq_only,
    ACTION_CENTER_NO_RECOGNIZED_SHEETS_MESSAGE,
    SKILLLAB_SUBMISSION_SHEET_SUBSTRING,
    CODELAB_SUBMISSION_SHEET_SUBSTRING,
    LAB_COMPLETION_SHEET_SUBSTRINGS,
)
from server.utils.bob_match import recalculate_bob_match, _normalize
from server.utils.cohort_participant_models import (
    apply_cohort_globals,
    participant_model,
    snapshot_cohort_globals,
)
from server.utils.cache import clear_cache, clear_dashboard_cache
from server.utils.skillboost_verify import verify_profile_url
from server.utils.audit import set_audit_session_vars
from server.utils.import_file_archive import archive_upload, ImportArchiveError
from datetime import date, datetime

bp = Blueprint('import', __name__)

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _per_sheet_block(module, sheet_name, importer_result, *, track=None, lab=None):
    """Build one entry for the per_sheet_errors response array.

    importer_result is the dict returned by an import_*() function. It MAY
    include 'rows_errors' (structured: list of {row, reason_code,
    reason_message, raw_email}). When absent we still emit a block with
    only counts so the UI can show 'sheet detected, no row issues'.
    """
    if importer_result is None:
        return None
    block = {
        'module': module,
        'sheet_name': sheet_name or '',
        'skipped': importer_result.get('skipped', 0) or 0,
        'created': importer_result.get('created', 0) or 0,
        'updated': importer_result.get('updated', 0) or 0,
        'total_rows': importer_result.get('total_rows', 0) or 0,
        'pii_auto_created': importer_result.get('pii_auto_created', 0) or 0,
        'pii_auto_skipped': importer_result.get('pii_auto_skipped', 0) or 0,
        'rows': [],
        'by_reason': [],
    }
    if track is not None:
        block['track'] = track
    if lab is not None:
        block['lab'] = lab

    rows_errors = importer_result.get('rows_errors') or []
    seen = []
    for r in rows_errors:
        if not isinstance(r, dict):
            continue
        seen.append({
            'row': r.get('row'),
            'reason_code': r.get('reason_code') or 'other',
            'reason_message': (r.get('reason_message') or '')[:300],
            'raw_email': (r.get('raw_email') or '')[:255],
        })
    block['rows'] = seen[:500]

    # Sample rows per reason (from capped row log)
    samples_by_reason = {}
    for r in seen:
        rc = r['reason_code']
        bucket = samples_by_reason.setdefault(rc, [])
        if len(bucket) < 5 and r['row'] is not None:
            bucket.append(r['row'])

    skip_reason_counts = importer_result.get('skip_reason_counts') or {}
    if isinstance(skip_reason_counts, dict) and skip_reason_counts:
        by_reason = []
        for rc, cnt in sorted(skip_reason_counts.items(), key=lambda kv: -int(kv[1] or 0)):
            try:
                n = int(cnt)
            except (TypeError, ValueError):
                n = 0
            by_reason.append({
                'reason_code': rc,
                'count': n,
                'sample_rows': samples_by_reason.get(rc, [])[:5],
            })
        block['by_reason'] = by_reason
    else:
        counts = {}
        for r in seen:
            rc = r['reason_code']
            d = counts.setdefault(rc, {'reason_code': rc, 'count': 0, 'sample_rows': []})
            d['count'] += 1
            if len(d['sample_rows']) < 5 and r['row'] is not None:
                d['sample_rows'].append(r['row'])
        block['by_reason'] = sorted(counts.values(), key=lambda d: -d['count'])
    return block


def _build_per_sheet_errors(*, profile_result=None, profile_sheet_name=None,
                            submission_result=None, submission_sheet_name=None,
                            codelab_result=None, codelab_sheet_name=None,
                            main_mcq_results=None,
                            optional_mcq_results=None,
                            lab_completion_results=None,
                            project_submission_results=None):
    """Aggregate every importer's structured row errors into one list.

    Each per-sheet block carries module/track/lab metadata, total counts and
    a 'by_reason' breakdown the import-result UI groups under the
    'Issues by sheet' panel.
    """
    out = []

    if profile_result and isinstance(profile_result, dict):
        block = _per_sheet_block('skillboost_profile', profile_sheet_name, profile_result)
        if block:
            out.append(block)

    if submission_result and isinstance(submission_result, dict) and 'error' not in submission_result:
        block = _per_sheet_block('skilllab_submission', submission_sheet_name, submission_result)
        if block:
            out.append(block)

    if codelab_result and isinstance(codelab_result, dict) and 'error' not in codelab_result:
        per_sheet = codelab_result.get('sheets')
        if per_sheet:
            for clr in per_sheet:
                if not isinstance(clr, dict) or 'error' in clr:
                    continue
                block = _per_sheet_block(
                    'codelab_submission', clr.get('sheet_name'), clr, track=clr.get('track'),
                )
                if block:
                    out.append(block)
        else:
            block = _per_sheet_block('codelab_submission', codelab_sheet_name, codelab_result)
            if block:
                out.append(block)

    for mcr in main_mcq_results or []:
        if not isinstance(mcr, dict) or 'error' in mcr:
            continue
        block = _per_sheet_block('main_mcq', mcr.get('sheet_name'), mcr, track=mcr.get('track'))
        if block:
            out.append(block)

    for omr in optional_mcq_results or []:
        if not isinstance(omr, dict) or 'error' in omr:
            continue
        block = _per_sheet_block('optional_mcq', omr.get('sheet_name'), omr, track=omr.get('track'))
        if block:
            out.append(block)

    for lcr in lab_completion_results or []:
        if not isinstance(lcr, dict) or 'error' in lcr:
            continue
        block = _per_sheet_block('lab_completion', lcr.get('sheet_name'), lcr,
                                 track=lcr.get('track'), lab=lcr.get('lab'))
        if block:
            out.append(block)

    for psr in project_submission_results or []:
        if not isinstance(psr, dict) or 'error' in psr:
            continue
        block = _per_sheet_block('project_submission', psr.get('sheet_name'), psr,
                                 track=psr.get('track'))
        if block:
            out.append(block)

    return out


def _require_cohort3_uts():
    """Return (error_response, status) if this request is not cohort 3; else (None, None)."""
    cohort_id = getattr(g, "cohort_id", None)
    if cohort_id != 3:
        return jsonify({
            "error": "UTS sync is only available for Cohort 3.",
            "cohort_id": cohort_id,
        }), 400
    return None, None


@bp.route("/uts-sync/status", methods=["GET"])
@require_page_access("import")
def uts_sync_status():
    """Last Cohort 3 UTS sync watermark / status."""
    err, code = _require_cohort3_uts()
    if err is not None:
        return err, code
    from server.utils.h2s_uts_sync import get_sync_status

    prefix = getattr(g, "table_prefix", None) or "cohort_3_"
    return jsonify({"ok": True, "status": get_sync_status(prefix)}), 200


@bp.route("/uts-sync", methods=["POST"])
@require_page_access("import")
def uts_sync_now():
    """On-demand Cohort 3 sync from Hack2Skill UTS APIs.

    Body/query ``full=true`` omits the registration ``start`` watermark and fetches all data.

    Prefer ``?stream=1`` (SSE). Sync often exceeds CDI/nginx proxy idle timeouts (~60s);
    heartbeats keep the gateway from returning HTTP 504 while work continues.
    """
    err, code = _require_cohort3_uts()
    if err is not None:
        return err, code
    from server.utils.h2s_uts_client import H2SUtsError
    from server.utils.h2s_uts_sync import (
        SYNC_KEY_LAST_SYNC_STATUS,
        run_cohort3_uts_sync,
        set_sync_value,
    )

    full = False
    if request.args.get("full", "").strip().lower() in ("1", "true", "yes"):
        full = True
    else:
        body = request.get_json(silent=True) or {}
        if isinstance(body, dict):
            raw = body.get("full")
            if raw is True or str(raw).strip().lower() in ("1", "true", "yes"):
                full = True

    prefix = getattr(g, "table_prefix", None) or "cohort_3_"
    use_stream = request.args.get("stream", "").strip().lower() in ("1", "true", "yes")

    if use_stream:
        progress_queue: queue.Queue = queue.Queue()
        app = current_app._get_current_object()
        cohort_snap = snapshot_cohort_globals()
        mode = "full" if full else "incremental"

        def run_sync():
            with app.app_context():
                apply_cohort_globals(cohort_snap[0], cohort_snap[1])
                try:
                    set_sync_value(
                        prefix,
                        SYNC_KEY_LAST_SYNC_STATUS,
                        f"running ({mode})",
                    )
                    result = run_cohort3_uts_sync(prefix=prefix, full=full)
                    progress_queue.put({"done": True, "result": result})
                except Exception as exc:
                    progress_queue.put({"done": True, "error": str(exc)[:1000]})

        thread = threading.Thread(target=run_sync, daemon=True)
        thread.start()

        def generate():
            while True:
                try:
                    item = progress_queue.get(timeout=0.5)
                except queue.Empty:
                    # Keepalive comment — nginx/CDI proxies treat this as activity.
                    yield ": keepalive\n\n"
                    continue
                if item.get("done"):
                    if "error" in item:
                        yield "data: " + json.dumps({"ok": False, "error": item["error"]}) + "\n\n"
                    else:
                        yield "data: " + json.dumps(item.get("result") or {}) + "\n\n"
                    break
            thread.join(timeout=5)

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    try:
        result = run_cohort3_uts_sync(prefix=prefix, full=full)
    except H2SUtsError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:500]}), 500

    # Partial runs (one of registrations/modules succeeded) still carry useful results,
    # so only report a transport-level failure when nothing at all was imported.
    nothing_succeeded = not result.get("registrations") and not result.get("modules")
    status = 502 if (not result.get("ok") and nothing_succeeded) else 200
    return jsonify(result), status


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

        try:
            archive_path = archive_upload(file, kind="main_import_preview")
        except ImportArchiveError as e:
            return jsonify({'error': str(e)}), 503

        df = parse_excel(archive_path)
        
        # Get Excel columns
        excel_columns = list(df.columns)
        
        # Auto-map fields
        auto_mappings = auto_map_fields(excel_columns)
        
        # Get first 5 rows as preview
        preview_rows = df.head(5).fillna('').to_dict('records')
        
        # Get DB fields for dropdown
        db_fields = get_db_fields()

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

        try:
            archive_path = archive_upload(file, kind="main_import")
        except ImportArchiveError as e:
            return jsonify({'error': str(e)}), 503

        filename = secure_filename(file.filename)
        file_path = archive_path

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
            cohort_snap = snapshot_cohort_globals()

            def progress_callback(created, updated, skipped):
                progress_queue.put({'created': created, 'updated': updated, 'skipped': skipped})

            def run_import():
                with app.app_context():
                    apply_cohort_globals(cohort_snap[0], cohort_snap[1])
                    try:
                        res = import_data(df, mappings, mode, progress_callback=progress_callback)
                        try:
                            recalculate_bob_match()
                        except Exception:
                            pass
                        try:
                            clear_dashboard_cache()
                        except Exception:
                            pass
                        progress_queue.put({'done': True, 'result': res})
                    except Exception as e:
                        progress_queue.put({'done': True, 'error': str(e)})

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
            clear_dashboard_cache()
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

        try:
            file_path = archive_upload(file, kind="bob")
        except ImportArchiveError as e:
            return jsonify({'error': str(e)}), 503

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
            return jsonify({'error': f'Error reading XLSX: {str(e)}'}), 400

        # Replace bob_companies: delete all then batch insert (cohort-prefixed table when applicable)
        Bob = participant_model(BobCompany)
        db.session.query(Bob).delete()
        db.session.commit()

        for i in range(0, len(company_names), BOB_INSERT_BATCH):
            batch = company_names[i:i + BOB_INSERT_BATCH]
            for name in batch:
                norm = _normalize(name)
                db.session.add(Bob(company_name=name, normalized_name=norm if norm else None))
            db.session.commit()

        updated = recalculate_bob_match()

        try:
            clear_dashboard_cache()
        except Exception:
            pass

        return jsonify({
            'companies_imported': len(company_names),
            'bob_match_updated': updated,
            'message': f'Imported {len(company_names)} companies and updated BOB match for {updated} profile(s).'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/bob/recalculate-matches', methods=['POST'])
@require_page_access('import')
def recalculate_bob_matches_only():
    """
    Recompute bob_match on user_pii and user_pii_injected from the cohort's bob_companies table.
    Use after loading cohort_*_bob_companies directly in SQL (BOB XLSX import already runs this).
    """
    try:
        from server.utils.bob_match import recalculate_bob_match

        updated = recalculate_bob_match()
        try:
            clear_dashboard_cache()
        except Exception:
            pass
        return jsonify({
            'bob_match_updated': updated,
            'message': f'Recalculated BOB match; {updated} row(s) updated.',
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

        try:
            file_path = archive_upload(file, kind="skillboost_preview")
        except ImportArchiveError as e:
            return jsonify({'error': str(e)}), 503

        cohort_id = getattr(g, 'cohort_id', None)
        preview = get_skillboost_preview(file_path, cohort_id=cohort_id)
        try:
            mapping = preview.get('sheet_mapping') or []
            missing = preview.get('missing_critical_modules') or []
            current_app.logger.info(
                "[skillboost_preview] cohort=%s tabs=%d detected=%d unrecognised=%d missing_critical=%d",
                cohort_id,
                len(mapping),
                sum(1 for r in mapping if r.get('status') == 'detected'),
                sum(1 for r in mapping if r.get('status') == 'unrecognised'),
                len(missing),
            )
        except Exception:
            pass
        return jsonify(preview), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/skillboost', methods=['POST'])
@require_page_access('import')
def import_skillboost_profiles():
    """
    Import Action Center XLSX (Skill Lab profile and/or other subsheets).
    Cohort 1: Skills profile sheet is optional when the workbook includes other recognized sheets
    (Main MCQ 16/17/18, optional MCQ, Skill Lab submission, Code Lab, lab completion, project submission).
    Cohort 2: without a profile sheet, imports Cohort 2 Optional MCQ only when that tab is present;
    otherwise behaves like Cohort 1 for non-profile subsheets (split Action Center exports).
    When a profile sheet is present, maps Email + profile link columns into skillboost_profile (does not
    overwrite rows where valid = TRUE).
    """
    try:
        if 'file' not in request.files and 'skillboost_file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files.get('file') or request.files.get('skillboost_file')
        if not file or file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only Excel files (.xlsx, .xls) are allowed for Skill Lab profile import'}), 400

        try:
            file_path = archive_upload(file, kind="skillboost_import")
        except ImportArchiveError as e:
            return jsonify({'error': str(e)}), 503

        cohort_id = getattr(g, 'cohort_id', None)

        sheets = load_all_skillboost_sheets(file_path, cohort_id=cohort_id)
        classification = sheets.get('classification') or {}
        sheet_mapping = classification.get('sheet_mapping') or []
        missing_critical_modules = classification.get('missing_critical_modules') or []

        # Confirmation gate: when critical modules are missing the client must
        # POST confirm_missing_modules=true after the user explicitly
        # acknowledges the warning in the preview UI.
        raw_confirm = (
            request.form.get('confirm_missing_modules')
            or request.values.get('confirm_missing_modules')
            or ''
        ).strip().lower()
        confirm_missing = raw_confirm in ('1', 'true', 'yes', 'on')
        if missing_critical_modules and not confirm_missing:
            return jsonify({
                'error': (
                    'Some expected Action Center subsheets are missing from this '
                    'workbook (see "missing_critical_modules"). Re-confirm the upload '
                    'to import only the detected sheets.'
                ),
                'sheet_mapping': sheet_mapping,
                'missing_critical_modules': missing_critical_modules,
                'requires_confirmation': True,
            }), 409

        try:
            from flask import current_app as _ca
            try:
                _ca.logger.info(
                    "[skillboost_import] cohort=%s tabs=%d detected=%d unrecognised=%d missing_critical=%d",
                    cohort_id,
                    len(sheet_mapping),
                    sum(1 for r in sheet_mapping if r.get('status') == 'detected'),
                    sum(1 for r in sheet_mapping if r.get('status') == 'unrecognised'),
                    len(missing_critical_modules),
                )
            except Exception:
                pass
        except Exception:
            pass

        # Cohort 2: no Skills profile sheet — if Optional MCQ is the only recognised subsheet,
        # import that only and return. When Code Lab / Skill Lab submission / other tabs are also
        # present, continue through the full import path below (same as Cohort 1).
        if cohort_id == 2 and (not sheets.get('profile_sheet_name') or sheets.get('profile_df') is None):
            c2 = sheets.get('cohort2_optional_mcq_sheet')
            c2df = c2.get('df') if c2 else None
            if cohort2_action_center_optional_mcq_only(sheets) and c2 and c2df is not None and len(c2df) > 0:
                optional_mcq_results = []
                optional_mcq_errors = []
                try:
                    try:
                        from server.utils.audit import set_audit_extra
                        set_audit_extra({
                            'source': 'optional_mcq_import_cohort2',
                            'filename': file.filename,
                            'sheet': c2.get('sheet_name'),
                        })
                    except Exception:
                        pass
                    omr = import_optional_mcq_response(
                        c2df, 4, score_from_sheet=True, allow_multiple_per_email=True
                    )
                    omr['track'] = 4
                    omr['sheet_name'] = c2.get('sheet_name')
                    optional_mcq_results.append(omr)
                except Exception as e:
                    optional_mcq_errors.append({
                        'track': 4,
                        'sheet_name': c2.get('sheet_name', ''),
                        'error': str(e),
                    })

                try:
                    clear_cache('_get_mcq_stats_cached')
                except Exception:
                    pass
                try:
                    clear_dashboard_cache()
                except Exception:
                    pass

                omr = optional_mcq_results[0] if optional_mcq_results else None
                response = {
                    'total_rows': omr['total_rows'] if omr else 0,
                    'created': omr['created'] if omr else 0,
                    'updated': omr['updated'] if omr else 0,
                    'skipped': omr['skipped'] if omr else 0,
                    'errors': omr.get('errors', []) if omr else [],
                    'message': '',
                }
                if omr:
                    response['message'] = (
                        f"Optional MCQ (Cohort 2): {omr['created']} created, {omr['updated']} updated, "
                        f"{omr['skipped']} skipped."
                    )
                elif optional_mcq_errors:
                    response['message'] = 'Optional MCQ (Cohort 2) import did not complete.'
                    response['errors'] = [optional_mcq_errors[0].get('error', 'Unknown error')]
                if optional_mcq_results:
                    response['mcq'] = []
                    for x in optional_mcq_results:
                        response['mcq'].append({
                            'track': x.get('track'),
                            'sheet_name': x.get('sheet_name', ''),
                            'total_rows': x['total_rows'],
                            'created': x['created'],
                            'updated': x['updated'],
                            'skipped': x['skipped'],
                            'errors': x.get('errors', []),
                        })
                if optional_mcq_errors:
                    response['mcq_errors'] = optional_mcq_errors

                response['sheet_mapping'] = sheet_mapping
                response['missing_critical_modules'] = missing_critical_modules
                response['per_sheet_errors'] = _build_per_sheet_errors(
                    profile_result=None,
                    profile_sheet_name=None,
                    submission_result=None,
                    submission_sheet_name=None,
                    codelab_result=None,
                    codelab_sheet_name=None,
                    main_mcq_results=[],
                    optional_mcq_results=optional_mcq_results,
                    lab_completion_results=[],
                    project_submission_results=[],
                )

                try:
                    from flask import current_app as _ca
                    for blk in response['per_sheet_errors']:
                        _ca.logger.info(
                            "[skillboost_import] module=%s track=%s lab=%s sheet=%r "
                            "created=%d updated=%d skipped=%d pii_auto_created=%d pii_auto_skipped=%d",
                            blk.get('module'), blk.get('track'), blk.get('lab'),
                            blk.get('sheet_name'),
                            blk.get('created') or 0,
                            blk.get('updated') or 0,
                            blk.get('skipped') or 0,
                            blk.get('pii_auto_created') or 0,
                            blk.get('pii_auto_skipped') or 0,
                        )
                except Exception:
                    pass

                return jsonify(response), 200

        has_profile = (
            sheets.get('profile_sheet_name')
            and sheets.get('profile_df') is not None
            and len(sheets['profile_df']) > 0
        )
        cohort_oneish = cohort_id in (1, None)
        profile_import_skipped = (not has_profile) and (cohort_oneish or cohort_id == 2)

        if profile_import_skipped:
            if not action_center_has_non_profile_imports(sheets):
                return jsonify({'error': ACTION_CENTER_NO_RECOGNIZED_SHEETS_MESSAGE}), 400
            result = {'total_rows': 0, 'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}
        else:
            if not has_profile:
                # Cohort 2 without profile is handled via profile_import_skipped when other sheets exist.
                if cohort_id != 2:
                    return jsonify({
                        'error': skillboost_sheet_not_found_message()
                        + ' Please use an XLSX from Google Skills Boost / Skill Lab (Action Center) export.',
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

        # Code Lab Submission (already loaded; Cohort 2 may have Student + Professional track tabs)
        codelab_result = None
        codelab_sheet = sheets.get('codelab_sheet_name')
        codelab_sheets = sheets.get('codelab_submission_sheets') or []
        if not codelab_sheets and sheets.get('codelab_df') is not None:
            codelab_sheets = [{
                'sheet_name': codelab_sheet,
                'df': sheets.get('codelab_df'),
                'track': None,
                'default_problem_statement': None,
            }]
        if codelab_sheets:
            try:
                from server.utils.audit import set_audit_extra
                set_audit_extra({
                    "source": "codelab_submission_import",
                    "filename": file.filename,
                    "sheets": [s.get('sheet_name') for s in codelab_sheets],
                })
            except Exception:
                pass
            try:
                codelab_result = import_codelab_submission_sheets(codelab_sheets)
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
                    # Cohort 2/3 question banks differ from C1 — use Action Center Score column.
                    mcr = import_main_mcq_response(
                        main_df, track, score_from_sheet=(not cohort_oneish),
                    )
                    mcr['track'] = track
                    mcr['sheet_name'] = main_sheet_name
                    main_mcq_results.append(mcr)
                else:
                    main_mcq_errors.append({'track': track, 'sheet_name': main_sheet_name, 'error': 'Sheet empty'})
            except Exception as main_err:
                main_mcq_errors.append({'track': track, 'sheet_name': main_sheet_name, 'error': str(main_err)})

        # Optional MCQ: Cohort 1 → tracks 1–3; Cohort 2 → "14.MCQ Optional" (track 4).
        optional_mcq_results = []
        optional_mcq_errors = []
        if cohort_oneish:
            for om in sheets.get('optional_mcq_sheets') or []:
                odf = om.get('df')
                if odf is None or len(odf) == 0:
                    continue
                try:
                    from server.utils.audit import set_audit_extra
                    set_audit_extra({
                        'source': 'optional_mcq_import',
                        'filename': file.filename,
                        'sheet': om.get('sheet_name'),
                        'track': om.get('track'),
                    })
                    omr = import_optional_mcq_response(odf, om['track'], score_from_sheet=False)
                    omr['track'] = om['track']
                    omr['sheet_name'] = om.get('sheet_name')
                    optional_mcq_results.append(omr)
                except Exception as e:
                    optional_mcq_errors.append({
                        'track': om.get('track'),
                        'sheet_name': om.get('sheet_name', ''),
                        'error': str(e),
                    })
        elif cohort_id == 2:
            c2 = sheets.get('cohort2_optional_mcq_sheet')
            c2df = c2.get('df') if c2 else None
            if c2 and c2df is not None and len(c2df) > 0:
                try:
                    from server.utils.audit import set_audit_extra
                    set_audit_extra({
                        'source': 'optional_mcq_import_cohort2',
                        'filename': file.filename,
                        'sheet': c2.get('sheet_name'),
                    })
                    omr = import_optional_mcq_response(
                        c2df, 4, score_from_sheet=True, allow_multiple_per_email=True
                    )
                    omr['track'] = 4
                    omr['sheet_name'] = c2.get('sheet_name')
                    optional_mcq_results.append(omr)
                except Exception as e:
                    optional_mcq_errors.append({
                        'track': 4,
                        'sheet_name': c2.get('sheet_name', ''),
                        'error': str(e),
                    })

        try:
            clear_dashboard_cache()
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
        if optional_mcq_results:
            try:
                clear_cache('_get_mcq_stats_cached')
            except Exception:
                pass
        if main_mcq_results:
            try:
                clear_cache('_get_main_mcq_stats_cached')
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

        if profile_import_skipped:
            response = {
                'total_rows': 0,
                'created': 0,
                'updated': 0,
                'skipped': 0,
                'errors': [],
                'message': (
                    'No Skill Lab profile sheet in workbook; imported other recognized subsheets only.'
                ),
            }
        else:
            response = {
                'total_rows': result['total_rows'],
                'created': result['created'],
                'updated': result['updated'],
                'skipped': result['skipped'],
                'errors': result.get('errors', []),
                'message': (
                    f"Imported Skill Lab profiles: {result['created']} created, "
                    f"{result['updated']} updated, {result['skipped']} skipped."
                ),
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

        if optional_mcq_results:
            response['mcq'] = []
            for omr in optional_mcq_results:
                response['mcq'].append({
                    'track': omr.get('track'),
                    'sheet_name': omr.get('sheet_name', ''),
                    'total_rows': omr['total_rows'],
                    'created': omr['created'],
                    'updated': omr['updated'],
                    'skipped': omr['skipped'],
                    'errors': omr.get('errors', []),
                })
                response['message'] += (
                    f" | Optional MCQ Track {omr.get('track')}: {omr['created']} created, "
                    f"{omr['updated']} updated, {omr['skipped']} skipped."
                )
        if optional_mcq_errors:
            response['mcq_errors'] = optional_mcq_errors

        response['sheet_mapping'] = sheet_mapping
        response['missing_critical_modules'] = missing_critical_modules
        response['per_sheet_errors'] = _build_per_sheet_errors(
            profile_result=(None if profile_import_skipped else result),
            profile_sheet_name=(None if profile_import_skipped else sheets.get('profile_sheet_name')),
            submission_result=submission_result,
            submission_sheet_name=submission_sheet,
            codelab_result=codelab_result,
            codelab_sheet_name=codelab_sheet,
            main_mcq_results=main_mcq_results,
            optional_mcq_results=optional_mcq_results,
            lab_completion_results=lab_completion_results,
            project_submission_results=project_submission_results,
        )

        try:
            from flask import current_app as _ca
            for blk in response['per_sheet_errors']:
                _ca.logger.info(
                    "[skillboost_import] module=%s track=%s lab=%s sheet=%r "
                    "created=%d updated=%d skipped=%d pii_auto_created=%d pii_auto_skipped=%d",
                    blk.get('module'), blk.get('track'), blk.get('lab'),
                    blk.get('sheet_name'),
                    blk.get('created') or 0,
                    blk.get('updated') or 0,
                    blk.get('skipped') or 0,
                    blk.get('pii_auto_created') or 0,
                    blk.get('pii_auto_skipped') or 0,
                )
        except Exception:
            pass

        return jsonify(response), 200
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

    from server.models import SkillboostProfile as _SkillboostBase

    SB = participant_model(_SkillboostBase)
    query = SB.query
    if pending_only:
        query = query.filter(SB.valid == False)
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
        clear_dashboard_cache()
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


def _parse_min_date_arg(raw):
    """Parse YYYY-MM-DD from query/form; return None if empty."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _verify_submission_worker(kind, row_id, url, problem_statement, min_date):
    """Run badge HTTP verification in a worker thread (own requests.Session)."""
    import requests
    from server.utils.badge_verify import verify_badge

    sess = requests.Session()
    try:
        return kind, row_id, verify_badge(
            url, problem_statement, min_date=min_date, session=sess
        )
    finally:
        try:
            sess.close()
        except Exception:
            pass


def _verify_submissions_stream(pending_only=False, min_date=None):
    """SSE: verify Skill Lab + Code Lab submission badge URLs (upload_screenshot)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from uuid import UUID

    SL = participant_model(SkillLabSubmission)
    CL = participant_model(CodeLabSubmission)

    sl_q = SL.query.filter(SL.upload_screenshot.isnot(None)).filter(SL.upload_screenshot != "")
    cl_q = CL.query.filter(CL.upload_screenshot.isnot(None)).filter(CL.upload_screenshot != "")
    if pending_only:
        sl_q = sl_q.filter(SL.valid == False)
        cl_q = cl_q.filter(CL.valid == False)

    work = []
    for r in sl_q.all():
        work.append(("sl", str(r.id), (r.upload_screenshot or "").strip(), r.problem_statement))
    for r in cl_q.all():
        work.append(("cl", str(r.id), (r.upload_screenshot or "").strip(), r.problem_statement))

    total = len(work)
    if total == 0:
        yield f"data: {json.dumps({'done': True, 'total': 0, 'verified_ok': 0, 'verified_fail': 0, 'pending': 0})}\n\n"
        return

    verified_ok = 0
    verified_fail = 0
    pending_n = 0
    current = 0
    workers = min(10, total)

    def _apply_result(kind, row_id, result):
        nonlocal verified_ok, verified_fail, pending_n
        try:
            uid = UUID(row_id)
        except ValueError:
            verified_fail += 1
            return
        rec = SL.query.get(uid) if kind == "sl" else CL.query.get(uid)
        if not rec:
            verified_fail += 1
            return
        try:
            status = (result or {}).get("status", "failed")
            rec.valid = status == "verified"
            rec.remark = ((result or {}).get("remarks") or "")[:8192]
            cd = (result or {}).get("completion_date")
            if cd:
                try:
                    d = date.fromisoformat(str(cd)[:10])
                    rec.completion_date = datetime(d.year, d.month, d.day)
                except ValueError:
                    rec.completion_date = None
            else:
                rec.completion_date = None
            rec.last_verified_at = datetime.utcnow()
            set_audit_session_vars()
            db.session.commit()
            if status == "verified":
                verified_ok += 1
            elif status == "pending":
                pending_n += 1
            else:
                verified_fail += 1
        except Exception:
            db.session.rollback()
            verified_fail += 1

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _verify_submission_worker,
                kind,
                row_id,
                url,
                problem_statement,
                min_date,
            ): (kind, row_id)
            for kind, row_id, url, problem_statement in work
        }
        for future in as_completed(futures):
            kind, row_id = futures[future]
            try:
                k, rid, result = future.result()
            except Exception:
                k, rid = kind, row_id
                result = {
                    "status": "pending",
                    "valid": False,
                    "remarks": "Pending: verification error",
                }
            _apply_result(k, rid, result)
            current += 1
            yield f"data: {json.dumps({'current': current, 'total': total, 'verified_ok': verified_ok, 'verified_fail': verified_fail, 'pending': pending_n})}\n\n"

    yield f"data: {json.dumps({'done': True, 'total': total, 'verified_ok': verified_ok, 'verified_fail': verified_fail, 'pending': pending_n})}\n\n"
    try:
        clear_cache("_get_skilllab_submission_stats_cached")
    except Exception:
        pass
    try:
        clear_cache("_get_codelab_submission_stats_cached")
    except Exception:
        pass
    try:
        clear_dashboard_cache()
    except Exception:
        pass


@bp.route("/submission/verify", methods=["POST", "GET"])
@require_page_access("import")
def verify_submissions():
    """
    Verify badge URLs on skilllab_submission and codelab_submission (upload_screenshot).
    SSE progress. Query: pending_only=1, min_date=YYYY-MM-DD (optional).
    """
    min_date_raw = request.args.get("min_date") or request.form.get("min_date") or ""
    min_date = _parse_min_date_arg(min_date_raw)
    if str(min_date_raw).strip() and min_date is None:
        return jsonify({"error": "Invalid min_date; use YYYY-MM-DD"}), 400
    pending_only = request.args.get("pending_only", "0") == "1"
    return Response(
        stream_with_context(_verify_submissions_stream(pending_only=pending_only, min_date=min_date)),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
