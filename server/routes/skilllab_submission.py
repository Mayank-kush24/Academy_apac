"""
Skill Lab Submission Verification page and API.
Interns access this page to manually verify team submissions,
toggling the 'valid' checkbox and adding remarks.
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from sqlalchemy import or_, func
from server.models import db, SkillLabSubmission
from server.utils.auth import get_current_user
from server.utils.permissions import require_page_access
from server.utils.audit import set_audit_session_vars

bp = Blueprint('skilllab_submission', __name__)


@bp.route('/stats', methods=['GET'])
@require_page_access('skilllab_submission')
def get_stats():
    """Return aggregate stats for Skill Lab submissions."""
    try:
        total = SkillLabSubmission.query.count() or 0
        verified = SkillLabSubmission.query.filter(SkillLabSubmission.valid == True).count() or 0
        pending = total - verified
        verification_rate = round(100.0 * verified / total, 1) if total > 0 else None

        return jsonify({
            'total_submissions': total,
            'verified_submissions': verified,
            'pending_submissions': pending,
            'verification_rate': verification_rate,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/list', methods=['GET'])
@require_page_access('skilllab_submission')
def list_submissions():
    """
    List Skill Lab submissions with pagination, search, and valid filter.
    Query params: search, valid (true/false/all), page, per_page.
    """
    try:
        search = request.args.get('search', '').strip()
        valid_filter = request.args.get('valid', '').strip().lower()
        problem_filter = request.args.get('problem_statement', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)

        query = SkillLabSubmission.query

        if search:
            query = query.filter(
                or_(
                    SkillLabSubmission.team_name.ilike(f'%{search}%'),
                    SkillLabSubmission.leader_name.ilike(f'%{search}%'),
                    SkillLabSubmission.leader_email.ilike(f'%{search}%'),
                )
            )

        if valid_filter == 'true':
            query = query.filter(SkillLabSubmission.valid == True)
        elif valid_filter == 'false':
            query = query.filter(SkillLabSubmission.valid == False)

        if problem_filter:
            query = query.filter(SkillLabSubmission.problem_statement.ilike(f'%{problem_filter}%'))

        query = query.order_by(SkillLabSubmission.created_at.desc())
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
    """A submission is considered reviewed once it has been saved with valid=True or a remark."""
    return submission.valid or (submission.remark and submission.remark.strip())


@bp.route('/<submission_id>/verify', methods=['PUT'])
@require_page_access('skilllab_submission')
def verify_submission(submission_id):
    """
    Update the valid flag and remark for a submission (intern verification).
    Body JSON: { "valid": true/false, "remark": "optional text" }
    Once reviewed, only admin users can edit.
    """
    try:
        submission = SkillLabSubmission.query.filter_by(id=submission_id).first()
        if not submission:
            return jsonify({'error': 'Submission not found'}), 404

        user = get_current_user()

        # If already reviewed, only admin can edit
        if _is_reviewed(submission):
            if not user or user.role != 'admin':
                return jsonify({'error': 'This submission has already been reviewed. Only admin users can modify it.'}), 403

        data = request.get_json() or {}
        if 'valid' in data:
            submission.valid = bool(data['valid'])
        if 'remark' in data:
            submission.remark = (data['remark'] or '').strip() or None

        # Record who verified
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
@require_page_access('skilllab_submission')
def get_filter_options():
    """Return distinct problem statements for filter dropdown."""
    try:
        problem_statements = [
            r[0] for r in db.session.query(SkillLabSubmission.problem_statement)
            .filter(
                SkillLabSubmission.problem_statement.isnot(None),
                SkillLabSubmission.problem_statement != ''
            )
            .distinct()
            .order_by(SkillLabSubmission.problem_statement)
            .all()
            if r[0]
        ]

        return jsonify({
            'problem_statements': problem_statements,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
