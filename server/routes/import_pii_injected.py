"""
Import page for user_pii_injected table only.
Not on nav/tracker; accessible only via URL path /import-user-pii-injected.
Accepts Excel (.xlsx, .xls) and CSV files.
"""
import json
import queue
import threading
import pandas as pd
from flask import Blueprint, request, jsonify, Response, stream_with_context, current_app
from server.utils.auth import get_current_user
from server.utils.permissions import require_role
from server.utils.excel_parser import (
    parse_excel,
    get_db_fields,
    auto_map_fields,
    import_data_injected,
)
from server.utils.cache import clear_cache
from server.utils.cohort_participant_models import apply_cohort_globals, snapshot_cohort_globals
from server.utils.import_file_archive import archive_upload, ImportArchiveError

bp = Blueprint('import_pii_injected', __name__)

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _load_dataframe(file_path):
    """Load Excel or CSV into a DataFrame."""
    path_lower = str(file_path).lower()
    if path_lower.endswith('.csv'):
        return pd.read_csv(file_path, encoding='utf-8', encoding_errors='replace')
    return parse_excel(file_path)


@bp.route('/preview', methods=['POST'])
@require_role('editor', 'admin')
def preview():
    """Preview Excel and return column mappings for user_pii_injected."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only Excel (.xlsx, .xls) or CSV files are allowed'}), 400

        try:
            file_path = archive_upload(file, kind="pii_injected_preview")
        except ImportArchiveError as e:
            return jsonify({'error': str(e)}), 503

        df = _load_dataframe(file_path)
        excel_columns = list(df.columns)
        auto_mappings = auto_map_fields(excel_columns)
        preview_rows = df.head(5).fillna('').to_dict('records')
        db_fields = get_db_fields()

        return jsonify({
            'excel_columns': excel_columns,
            'preview_rows': preview_rows,
            'auto_mappings': auto_mappings,
            'db_fields': db_fields,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/execute', methods=['POST'])
@require_role('editor', 'admin')
def execute():
    """Execute import into user_pii_injected."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only Excel (.xlsx, .xls) or CSV files are allowed'}), 400

        mappings_json = request.form.get('mappings')
        mode = request.form.get('mode', 'create')
        if not mappings_json:
            return jsonify({'error': 'Field mappings are required'}), 400
        mappings = json.loads(mappings_json)
        if mode not in ('create', 'create_update', 'update_only'):
            return jsonify({'error': 'Invalid import mode'}), 400

        try:
            file_path = archive_upload(file, kind="pii_injected")
        except ImportArchiveError as e:
            return jsonify({'error': str(e)}), 503

        df = _load_dataframe(file_path)

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
                        res = import_data_injected(df, mappings, mode, progress_callback=progress_callback)
                        try:
                            clear_cache()
                        except Exception:
                            pass
                        progress_queue.put({'done': True, 'result': res})
                    except Exception as e:
                        progress_queue.put({'done': True, 'error': str(e)})

            threading.Thread(target=run_import).start()

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

            return Response(
                stream_with_context(generate()),
                mimetype='text/event-stream',
                headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'},
            )

        result = import_data_injected(df, mappings, mode)
        try:
            clear_cache()
        except Exception:
            pass
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
