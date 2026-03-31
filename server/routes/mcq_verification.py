"""
Optional MCQ Verification page and API.
Interns verify participant MCQ completion: valid checkbox and remark.
Once reviewed, only admin can edit.
"""
import csv
import io
from datetime import datetime
from flask import Blueprint, request, jsonify, Response
from sqlalchemy import or_
from server.models import db, OptionalMcqVerification, OptionalMcqResponse, MainMcqResponse, UserPII
from server.utils.auth import get_current_user
from server.utils.permissions import require_page_access
from server.utils.audit import set_audit_session_vars
from server.utils.mcq_answer_key import score_submission, get_track_questions, get_response_score
from server.utils.main_mcq_answer_key import get_track_questions as main_get_track_questions, score_submission as main_score_submission
from server.utils.cache import cache_result

bp = Blueprint('mcq_verification', __name__)


@cache_result(ttl=900)
def _get_mcq_stats_cached():
    """Compute MCQ stats (expensive); cached 15 min. Clear on MCQ import."""
    total = OptionalMcqResponse.query.count() or 0
    auto_passed = 0
    if total > 0:
        for r in OptionalMcqResponse.query.all():
            auto = get_response_score(r)
            if auto['correct_count'] >= 8:
                auto_passed += 1
    pending = max(0, total - auto_passed)
    auto_pass_rate = round(100.0 * auto_passed / total, 1) if total > 0 else None
    return {
        'total_submissions': total,
        'auto_passed': auto_passed,
        'pending_submissions': pending,
        'auto_pass_rate': auto_pass_rate,
    }


@bp.route('/stats', methods=['GET'])
@require_page_access('optional_mcq_verification')
def get_stats():
    """Return aggregate stats: total, auto-passed (8+/10), rates (cached 5 min)."""
    try:
        data = _get_mcq_stats_cached()
        return jsonify(data), 200
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
            auto = get_response_score(r)
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


def _build_export_rows(query, passed_only=False):
    """Build list of dicts with name, email, track_number, score_display for CSV export."""
    rows = []
    for r in query.order_by(OptionalMcqResponse.track_number.asc(), OptionalMcqResponse.email.asc()).all():
        auto = get_response_score(r)
        if passed_only and auto['correct_count'] < 6:
            continue
        name = (r.participant.name if r.participant else None) or r.leader_name or ''
        rows.append({
            'name': name or '',
            'email': r.email or '',
            'track': r.track_number,
            'score': auto['score_display'],
        })
    return rows


@bp.route('/responses/export', methods=['GET'])
@require_page_access('optional_mcq_verification')
def export_responses():
    """
    Export Optional MCQ responses as CSV: name, email, track, score.
    Query param: passed_only=1 to export only 6/10 or above (60%+); otherwise all.
    """
    try:
        passed_only = request.args.get('passed_only', '0').strip() == '1'
        query = OptionalMcqResponse.query.outerjoin(
            UserPII, OptionalMcqResponse.email == UserPII.email
        )
        rows = _build_export_rows(query, passed_only=passed_only)

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['Name', 'Email', 'Track', 'Score'])
        for r in rows:
            # Force score as text so Excel does not interpret "8/10" as a date
            score_val = r['score'] or ''
            score_text = ('="' + str(score_val).replace('"', '""') + '"') if score_val else ''
            writer.writerow([
                r['name'],
                r['email'],
                r['track'],
                score_text,
            ])
        buf.seek(0)
        filename = 'optional-mcq-passed-6plus.csv' if passed_only else 'optional-mcq-all.csv'
        return Response(
            buf.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
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


# ----- Main MCQ (MCQ Verification) -----

@cache_result(ttl=900)
def _get_main_mcq_stats_cached():
    """Main MCQ stats: total and passed (score >= 6) per track."""
    try:
        by_track = []
        for track_num in (1, 2, 3):
            total = MainMcqResponse.query.filter(MainMcqResponse.track_number == track_num).count()
            passed = MainMcqResponse.query.filter(
                MainMcqResponse.track_number == track_num,
                MainMcqResponse.score >= 6
            ).count()
            by_track.append({'track': track_num, 'total': total, 'passed_6': passed})
        total_all = MainMcqResponse.query.count()
        passed_all = MainMcqResponse.query.filter(MainMcqResponse.score >= 6).count()
        rate = round(100.0 * passed_all / total_all, 1) if total_all else None
        return {
            'main_mcq_by_track': by_track,
            'total_submissions': total_all,
            'passed_6': passed_all,
            'auto_pass_rate': rate,
        }
    except Exception:
        return {
            'main_mcq_by_track': [{'track': t, 'total': 0, 'passed_6': 0} for t in (1, 2, 3)],
            'total_submissions': 0,
            'passed_6': 0,
            'auto_pass_rate': None,
        }


@bp.route('/main/stats', methods=['GET'])
@require_page_access('mcq_verification')
def get_main_stats():
    """Return main MCQ stats (total, passed 6+ per track, rate)."""
    try:
        data = _get_main_mcq_stats_cached()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/main/responses/list', methods=['GET'])
@require_page_access('mcq_verification')
def list_main_responses():
    """
    List Main MCQ responses with pagination, search, track filter.
    Returns score, score_display, results from main answer key.
    """
    try:
        search = request.args.get('search', '').strip()
        track_filter = request.args.get('track', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)

        query = MainMcqResponse.query.outerjoin(UserPII, MainMcqResponse.email == UserPII.email)

        if search:
            query = query.filter(
                or_(
                    MainMcqResponse.email.ilike(f'%{search}%'),
                    MainMcqResponse.leader_name.ilike(f'%{search}%'),
                    UserPII.name.ilike(f'%{search}%'),
                )
            )
        if track_filter and track_filter in ('1', '2', '3'):
            query = query.filter(MainMcqResponse.track_number == int(track_filter))

        query = query.order_by(MainMcqResponse.track_number.asc(), MainMcqResponse.email.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        rows = []
        for r in pagination.items:
            d = r.to_dict()
            d['name'] = r.participant.name if r.participant else None
            d['score'] = r.score
            d['score_display'] = f'{r.score}/10' if r.score is not None else '—'
            # Recompute results for display (per-question correct/incorrect)
            auto = main_score_submission(
                r.track_number,
                r.question_1, r.question_2, r.question_3, r.question_4,
                r.question_5, r.question_6, r.question_7, r.question_8,
                r.question_9, r.question_10,
            )
            d['results'] = auto.get('results', [])
            d['passed'] = (r.score or 0) >= 6
            d['question_labels'] = main_get_track_questions(r.track_number)
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


@bp.route('/main/export', methods=['GET'])
@require_page_access('mcq_verification')
def export_main_responses():
    """Export Main MCQ responses as CSV: name, email, track, score. passed_only=1 for score >= 6."""
    try:
        passed_only = request.args.get('passed_only', '0').strip() == '1'
        query = MainMcqResponse.query.outerjoin(UserPII, MainMcqResponse.email == UserPII.email)
        query = query.order_by(MainMcqResponse.track_number.asc(), MainMcqResponse.email.asc())
        rows = []
        for r in query.all():
            if passed_only and (r.score is None or r.score < 6):
                continue
            name = (r.participant.name if r.participant else None) or r.leader_name or ''
            rows.append({
                'name': name or '',
                'email': r.email or '',
                'track': r.track_number,
                'score': f'{r.score}/10' if r.score is not None else '—',
            })

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['Name', 'Email', 'Track', 'Score'])
        for r in rows:
            score_val = r['score'] or ''
            score_text = ('="' + str(score_val).replace('"', '""') + '"') if score_val else ''
            writer.writerow([r['name'], r['email'], r['track'], score_text])
        buf.seek(0)
        filename = 'mcq-verification-passed-6plus.csv' if passed_only else 'mcq-verification-all.csv'
        return Response(
            buf.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
