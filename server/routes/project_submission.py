"""
Project Submission Verification page and API (final project per track).
"""
from datetime import datetime

import pandas as pd
from flask import Blueprint, request, jsonify, g
from sqlalchemy import or_, and_
from server.models import db, ProjectSubmission
from server.utils.cohort_participant_models import participant_model
from server.utils.auth import get_current_user
from server.utils.permissions import require_page_access
from server.utils.audit import set_audit_session_vars
from server.utils.cache import cache_result, clear_cache
from server.utils.excel_parser import import_project_submission_scores, _parse_project_score_value
from server.utils.import_file_archive import archive_upload, ImportArchiveError

bp = Blueprint('project_submission', __name__)


def _PS():
    """Return ProjectSubmission model for the current cohort."""
    return participant_model(ProjectSubmission)


@cache_result(ttl=900)
def _get_project_submission_stats_cached(table_prefix=''):
    """Cached stats (15 min) keyed by cohort table_prefix."""
    PS = participant_model(ProjectSubmission)
    total = PS.query.count() or 0
    verified = PS.query.filter(PS.valid == True).count() or 0
    reviewed = PS.query.filter(
        or_(
            PS.valid == True,
            and_(
                PS.remark.isnot(None),
                PS.remark != '',
            ),
        )
    ).count() or 0
    pending = max(0, total - reviewed)
    verification_rate = round(100.0 * verified / total, 1) if total > 0 else None
    return {
        'total_submissions': total,
        'verified_submissions': verified,
        'pending_submissions': pending,
        'verification_rate': verification_rate,
    }


@bp.route('/stats', methods=['GET'])
@require_page_access('project_submission')
def get_stats():
    try:
        data = _get_project_submission_stats_cached(table_prefix=getattr(g, 'table_prefix', ''))
        return jsonify(data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/list', methods=['GET'])
@require_page_access('project_submission')
def list_submissions():
    try:
        search = request.args.get('search', '').strip()
        valid_filter = request.args.get('valid', '').strip().lower()
        problem_filter = request.args.get('problem_statement', '').strip()
        track_param = request.args.get('track', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)

        PS = _PS()
        query = PS.query

        if search:
            query = query.filter(
                or_(
                    PS.team_name.ilike(f'%{search}%'),
                    PS.leader_name.ilike(f'%{search}%'),
                    PS.leader_email.ilike(f'%{search}%'),
                )
            )

        if valid_filter == 'true':
            query = query.filter(PS.valid == True)
        elif valid_filter == 'false':
            query = query.filter(
                PS.valid == False,
                or_(
                    PS.remark.is_(None),
                    PS.remark == '',
                ),
            )

        if problem_filter:
            query = query.filter(PS.problem_statement.ilike(f'%{problem_filter}%'))

        if track_param in ('1', '2', '3'):
            query = query.filter(PS.track_number == int(track_param))

        query = query.order_by(PS.created_at.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        rows = [row.to_dict() for row in pagination.items]

        return jsonify({
            'rows': rows,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _is_reviewed(submission):
    return submission.valid or (submission.remark and submission.remark.strip())


@bp.route('/<submission_id>/verify', methods=['PUT'])
@require_page_access('project_submission')
def verify_submission(submission_id):
    try:
        PS = _PS()
        submission = PS.query.filter_by(id=submission_id).first()
        if not submission:
            return jsonify({'error': 'Submission not found'}), 404

        user = get_current_user()

        if _is_reviewed(submission):
            if not user or user.role != 'admin':
                return jsonify({'error': 'This submission has already been reviewed. Only admin users can modify it.'}), 403

        data = request.get_json() or {}
        if 'valid' in data:
            submission.valid = bool(data['valid'])
        if 'remark' in data:
            submission.remark = (data['remark'] or '').strip() or None
        if 'score' in data:
            raw = data.get('score')
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                submission.score = None
            else:
                parsed = _parse_project_score_value(raw)
                if parsed is None:
                    return jsonify({'error': 'Invalid score; use a number or null to clear.'}), 400
                submission.score = parsed

        if user:
            submission.updated_by_name = user.name
            submission.updated_by_email = user.email
        submission.updated_at = datetime.utcnow()

        set_audit_session_vars()
        db.session.commit()

        return jsonify({'submission': submission.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/filters', methods=['GET'])
@require_page_access('project_submission')
def get_filter_options():
    try:
        PS = _PS()
        problem_statements = [
            r[0] for r in db.session.query(PS.problem_statement)
            .filter(
                PS.problem_statement.isnot(None),
                PS.problem_statement != ''
            )
            .distinct()
            .order_by(PS.problem_statement)
            .all()
            if r[0]
        ]

        return jsonify({
            'problem_statements': problem_statements,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/import-scores', methods=['POST'])
@require_page_access('project_submission')
def import_scores():
    """
    Upload a CSV or Excel with leader email + score for one track; updates existing
    project_submission rows only (one import per track file).
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        upload = request.files['file']
        if not upload.filename:
            return jsonify({'error': 'No file selected'}), 400
        ext = upload.filename.rsplit('.', 1)[-1].lower() if '.' in upload.filename else ''
        if ext not in ('csv', 'xlsx', 'xls'):
            return jsonify({'error': 'Upload a .csv, .xlsx, or .xls file'}), 400

        track_raw = (request.form.get('track_number') or request.form.get('track') or '').strip()
        try:
            track_number = int(track_raw)
        except ValueError:
            return jsonify({'error': 'Form field track_number is required (1, 2, or 3)'}), 400
        if track_number not in (1, 2, 3):
            return jsonify({'error': 'track_number must be 1, 2, or 3'}), 400

        try:
            archive_path = archive_upload(upload, kind="project_scores")
        except ImportArchiveError as e:
            return jsonify({'error': str(e)}), 503

        if ext == 'csv':
            df = pd.read_csv(archive_path, encoding='utf-8', encoding_errors='replace')
        else:
            df = pd.read_excel(archive_path)

        user = get_current_user()
        audit_user = None
        if user:
            audit_user = {'name': user.name, 'email': user.email}

        set_audit_session_vars()
        result = import_project_submission_scores(
            df, track_number=track_number, audit_user=audit_user
        )
        try:
            clear_cache('_get_project_submission_stats_cached')
        except Exception:
            pass

        return jsonify(result), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
