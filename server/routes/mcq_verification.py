"""
Optional MCQ Verification page and API.
Interns verify participant MCQ completion: valid checkbox and remark.
Once reviewed, only admin can edit.
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from sqlalchemy import or_
from server.models import db, OptionalMcqVerification, OptionalMcqResponse, UserPII
from server.utils.auth import get_current_user
from server.utils.permissions import require_page_access
from server.utils.audit import set_audit_session_vars
from server.utils.mcq_answer_key import score_submission, get_track_questions

bp = Blueprint('mcq_verification', __name__)


@bp.route('/stats', methods=['GET'])
@require_page_access('optional_mcq_verification')
def get_stats():
    """Return aggregate stats: total, auto-passed (8+/10), manual verified, rates."""
    try:
        total = OptionalMcqResponse.query.count() or 0

        # Auto verification: count submissions that score 8+ correct
        auto_passed = 0
        if total > 0:
            for r in OptionalMcqResponse.query.all():
                auto = score_submission(
                    r.track_number,
                    getattr(r, 'question_1', None), getattr(r, 'question_2', None),
                    getattr(r, 'question_3', None), getattr(r, 'question_4', None),
                    getattr(r, 'question_5', None), getattr(r, 'question_6', None),
                    getattr(r, 'question_7', None), getattr(r, 'question_8', None),
                    getattr(r, 'question_9', None), getattr(r, 'question_10', None),
                )
                if auto['correct_count'] >= 8:
                    auto_passed += 1
        pending = max(0, total - auto_passed)
        auto_pass_rate = round(100.0 * auto_passed / total, 1) if total > 0 else None

        return jsonify({
            'total_submissions': total,
            'auto_passed': auto_passed,
            'pending_submissions': pending,
            'auto_pass_rate': auto_pass_rate,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/responses/list', methods=['GET'])
@require_page_access('optional_mcq_verification')
def list_responses():
    """
    List Optional MCQ responses (imported from XLSX): track, email, name, question_1..question_10.
    Query params: search, track (1/2/3), page, per_page.
    """
    try:
        search = request.args.get('search', '').strip()
        track_filter = request.args.get('track', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)

        query = OptionalMcqResponse.query.outerjoin(UserPII, OptionalMcqResponse.email == UserPII.email)

        if search:
            query = query.filter(
                or_(
                    OptionalMcqResponse.email.ilike(f'%{search}%'),
                    OptionalMcqResponse.leader_name.ilike(f'%{search}%'),
                    UserPII.name.ilike(f'%{search}%'),
                )
            )
        if track_filter and track_filter in ('1', '2', '3'):
            query = query.filter(OptionalMcqResponse.track_number == int(track_filter))

        query = query.order_by(OptionalMcqResponse.track_number.asc(), OptionalMcqResponse.email.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        rows = []
        for r in pagination.items:
            d = r.to_dict()
            d['name'] = r.participant.name if r.participant else None
            # Auto verification: score against answer key (correct / 10)
            auto = score_submission(
                r.track_number,
                getattr(r, 'question_1', None),
                getattr(r, 'question_2', None),
                getattr(r, 'question_3', None),
                getattr(r, 'question_4', None),
                getattr(r, 'question_5', None),
                getattr(r, 'question_6', None),
                getattr(r, 'question_7', None),
                getattr(r, 'question_8', None),
                getattr(r, 'question_9', None),
                getattr(r, 'question_10', None),
            )
            d['score'] = auto['correct_count']
            d['score_display'] = auto['score_display']
            d['verification_results'] = auto['results']
            d['passed'] = auto['correct_count'] >= 8
            d['question_labels'] = get_track_questions(r.track_number)
            rows.append(d)

        return jsonify({
            'rows': rows,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/list', methods=['GET'])
@require_page_access('optional_mcq_verification')
def list_entries():
    """
    List Optional MCQ verification entries with pagination, search, and valid filter.
    Query params: search, valid (true/false/all), page, per_page.
    """
    try:
        search = request.args.get('search', '').strip()
        valid_filter = request.args.get('valid', '').strip().lower()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)

        query = OptionalMcqVerification.query

        if search:
            query = query.filter(
                or_(
                    OptionalMcqVerification.name.ilike(f'%{search}%'),
                    OptionalMcqVerification.email.ilike(f'%{search}%'),
                )
            )

        if valid_filter == 'true':
            query = query.filter(OptionalMcqVerification.valid == True)
        elif valid_filter == 'false':
            query = query.filter(OptionalMcqVerification.valid == False)

        query = query.order_by(OptionalMcqVerification.created_at.desc())
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


def _is_reviewed(entry):
    """An entry is considered reviewed once valid=True or remark is non-empty."""
    return entry.valid or (entry.remark and entry.remark.strip())


@bp.route('/<entry_id>/verify', methods=['PUT'])
@require_page_access('optional_mcq_verification')
def verify_entry(entry_id):
    """
    Update valid and remark for an MCQ verification entry.
    Body JSON: { "valid": true/false, "remark": "optional text" }
    Once reviewed, only admin can edit.
    """
    try:
        entry = OptionalMcqVerification.query.filter_by(id=entry_id).first()
        if not entry:
            return jsonify({'error': 'Entry not found'}), 404

        user = get_current_user()

        if _is_reviewed(entry):
            if not user or user.role != 'admin':
                return jsonify({'error': 'This entry has already been reviewed. Only admin users can modify it.'}), 403

        data = request.get_json() or {}
        if 'valid' in data:
            entry.valid = bool(data['valid'])
        if 'remark' in data:
            entry.remark = (data['remark'] or '').strip() or None

        if user:
            entry.updated_by_name = user.name
            entry.updated_by_email = user.email
        entry.updated_at = datetime.utcnow()

        set_audit_session_vars()
        db.session.commit()

        return jsonify({'entry': entry.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('', methods=['POST'])
@require_page_access('optional_mcq_verification')
def create_entry():
    """
    Create a new MCQ verification entry (e.g. add participant by email).
    Body JSON: { "email": "required", "name": "optional" }
    """
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip()
        if not email:
            return jsonify({'error': 'Email is required'}), 400

        existing = OptionalMcqVerification.query.filter_by(email=email).first()
        if existing:
            return jsonify({'error': 'An entry for this email already exists', 'entry': existing.to_dict()}), 409

        name = (data.get('name') or '').strip() or None
        if not name:
            profile = UserPII.query.filter_by(email=email).first()
            if profile and profile.name:
                name = profile.name

        user = get_current_user()
        entry = OptionalMcqVerification(
            email=email,
            name=name,
            created_by_name=user.name if user else None,
            created_by_email=user.email if user else None,
        )
        db.session.add(entry)
        set_audit_session_vars()
        db.session.commit()

        return jsonify({'entry': entry.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
