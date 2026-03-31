"""
Project Submission Verification page and API (final project per track).
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from sqlalchemy import or_, and_
from server.models import db, ProjectSubmission
from server.utils.auth import get_current_user
from server.utils.permissions import require_page_access
from server.utils.audit import set_audit_session_vars
from server.utils.cache import cache_result

bp = Blueprint('project_submission', __name__)


@cache_result(ttl=900)
def _get_project_submission_stats_cached():
    """Cached stats (15 min). Cleared on import."""
    total = ProjectSubmission.query.count() or 0
    verified = ProjectSubmission.query.filter(ProjectSubmission.valid == True).count() or 0
    reviewed = ProjectSubmission.query.filter(
        or_(
            ProjectSubmission.valid == True,
            and_(
                ProjectSubmission.remark.isnot(None),
                ProjectSubmission.remark != '',
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
        data = _get_project_submission_stats_cached()
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

        query = ProjectSubmission.query

        if search:
            query = query.filter(
                or_(
                    ProjectSubmission.team_name.ilike(f'%{search}%'),
                    ProjectSubmission.leader_name.ilike(f'%{search}%'),
                    ProjectSubmission.leader_email.ilike(f'%{search}%'),
                )
            )

        if valid_filter == 'true':
            query = query.filter(ProjectSubmission.valid == True)
        elif valid_filter == 'false':
            query = query.filter(
                ProjectSubmission.valid == False,
                or_(
                    ProjectSubmission.remark.is_(None),
                    ProjectSubmission.remark == '',
                ),
            )

        if problem_filter:
            query = query.filter(ProjectSubmission.problem_statement.ilike(f'%{problem_filter}%'))

        if track_param in ('1', '2', '3'):
            query = query.filter(ProjectSubmission.track_number == int(track_param))

        query = query.order_by(ProjectSubmission.created_at.desc())
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
        submission = ProjectSubmission.query.filter_by(id=submission_id).first()
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
        problem_statements = [
            r[0] for r in db.session.query(ProjectSubmission.problem_statement)
            .filter(
                ProjectSubmission.problem_statement.isnot(None),
                ProjectSubmission.problem_statement != ''
            )
            .distinct()
            .order_by(ProjectSubmission.problem_statement)
            .all()
            if r[0]
        ]

        return jsonify({
            'problem_statements': problem_statements,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
