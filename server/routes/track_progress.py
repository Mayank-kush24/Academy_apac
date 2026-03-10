"""
Track Progress Query page — filter users by their track progress grid status.
Supports filtering by Webinar, Optional MCQ, Code Lab, and Skill Lab status per track.
"""
import io
from collections import defaultdict

from flask import Blueprint, request, jsonify, Response
from sqlalchemy import or_, and_
from server.models import (
    db, UserPIICombined, CodeLabSubmission, SkillLabSubmission, OptionalMcqResponse,
)
from server.utils.auth import get_current_user
from server.utils.permissions import require_page_access

bp = Blueprint('track_progress', __name__)

TRACK_NUMBERS = (1, 2, 3)
TRACK_LABELS = {1: 'Track 1', 2: 'Track 2', 3: 'Track 3'}


def _build_codelab_exists(track, extra_filters=None):
    """Return an EXISTS clause for CodeLabSubmission on a given track."""
    conditions = [
        CodeLabSubmission.leader_email == UserPIICombined.email,
        CodeLabSubmission.track_number == track,
    ]
    if extra_filters:
        conditions.extend(extra_filters)
    return db.session.query(CodeLabSubmission.id).filter(*conditions).exists()


def _build_skilllab_exists(track, extra_filters=None):
    """Return an EXISTS clause for SkillLabSubmission on a given track (via problem_statement)."""
    label = TRACK_LABELS[track]
    conditions = [
        SkillLabSubmission.leader_email == UserPIICombined.email,
        SkillLabSubmission.problem_statement.ilike(f'%{label}%'),
    ]
    if extra_filters:
        conditions.extend(extra_filters)
    return db.session.query(SkillLabSubmission.id).filter(*conditions).exists()


def _build_optmcq_exists(track, extra_filters=None):
    """Return an EXISTS clause for OptionalMcqResponse on a given track."""
    conditions = [
        OptionalMcqResponse.email == UserPIICombined.email,
        OptionalMcqResponse.track_number == track,
    ]
    if extra_filters:
        conditions.extend(extra_filters)
    return db.session.query(OptionalMcqResponse.id).filter(*conditions).exists()


def _apply_track_filters(query, args):
    """Parse track-progress filter params and append WHERE conditions to the query."""
    for t in TRACK_NUMBERS:
        # --- Webinar (derived from codelab existence) ---
        val = args.get(f'webinar_t{t}', '').strip().lower()
        if val == 'valid':
            query = query.filter(_build_codelab_exists(t))
        elif val == 'empty':
            query = query.filter(~_build_codelab_exists(t))

        # --- Optional MCQ ---
        val = args.get(f'opt_mcq_t{t}', '').strip().lower()
        if val == 'pass':
            query = query.filter(_build_optmcq_exists(t, [OptionalMcqResponse.score >= 6]))
        elif val == 'fail':
            query = query.filter(_build_optmcq_exists(t, [OptionalMcqResponse.score < 6]))
        elif val == 'empty':
            query = query.filter(~_build_optmcq_exists(t))

        # --- Code Lab ---
        val = args.get(f'codelab_t{t}', '').strip().lower()
        if val == 'valid':
            query = query.filter(_build_codelab_exists(t, [CodeLabSubmission.valid == True]))
        elif val == 'not_valid':
            query = query.filter(_build_codelab_exists(t, [
                CodeLabSubmission.valid == False,
                CodeLabSubmission.remark.isnot(None),
                CodeLabSubmission.remark != '',
            ]))
        elif val == 'pending':
            query = query.filter(_build_codelab_exists(t, [
                CodeLabSubmission.valid == False,
                or_(CodeLabSubmission.remark.is_(None), CodeLabSubmission.remark == ''),
            ]))
        elif val == 'empty':
            query = query.filter(~_build_codelab_exists(t))

        # --- Skill Lab ---
        val = args.get(f'skilllab_t{t}', '').strip().lower()
        if val == 'valid':
            query = query.filter(_build_skilllab_exists(t, [SkillLabSubmission.valid == True]))
        elif val == 'not_valid':
            query = query.filter(_build_skilllab_exists(t, [
                SkillLabSubmission.valid == False,
                SkillLabSubmission.remark.isnot(None),
                SkillLabSubmission.remark != '',
            ]))
        elif val == 'pending':
            query = query.filter(_build_skilllab_exists(t, [
                SkillLabSubmission.valid == False,
                or_(SkillLabSubmission.remark.is_(None), SkillLabSubmission.remark == ''),
            ]))
        elif val == 'empty':
            query = query.filter(~_build_skilllab_exists(t))

    return query


def _compute_grid_bulk(emails):
    """Bulk-compute the track progress grid for a list of emails.
    Returns {email: {webinar_t1: '...', codelab_t1: '...', ...}} .
    """
    if not emails:
        return {}

    codelab_map = defaultdict(list)
    for c in CodeLabSubmission.query.filter(CodeLabSubmission.leader_email.in_(emails)).all():
        codelab_map[c.leader_email].append(c)

    skilllab_map = defaultdict(list)
    for s in SkillLabSubmission.query.filter(SkillLabSubmission.leader_email.in_(emails)).all():
        skilllab_map[s.leader_email].append(s)

    optmcq_map = defaultdict(list)
    for o in OptionalMcqResponse.query.filter(OptionalMcqResponse.email.in_(emails)).all():
        optmcq_map[o.email].append(o)

    result = {}
    for email in emails:
        grid = {}
        for t in TRACK_NUMBERS:
            label = TRACK_LABELS[t]

            # Webinar
            has_codelab = any(c.track_number == t for c in codelab_map.get(email, []))
            grid[f'webinar_t{t}'] = 'Valid' if has_codelab else ''

            # Optional MCQ
            mcq_match = next((o for o in optmcq_map.get(email, []) if o.track_number == t), None)
            if mcq_match:
                score = mcq_match.score if mcq_match.score is not None else 0
                grid[f'opt_mcq_t{t}'] = 'Pass' if score >= 6 else 'Fail'
            else:
                grid[f'opt_mcq_t{t}'] = ''

            # Code Lab
            cl_matches = [c for c in codelab_map.get(email, []) if c.track_number == t]
            if cl_matches:
                valid_cnt = sum(1 for c in cl_matches if c.valid)
                invalid_cnt = sum(1 for c in cl_matches if not c.valid and c.remark and c.remark.strip())
                pending_cnt = len(cl_matches) - valid_cnt - invalid_cnt
                parts = []
                if valid_cnt:
                    parts.append(f'{valid_cnt} Valid')
                if invalid_cnt:
                    parts.append(f'{invalid_cnt} Not Valid')
                if pending_cnt:
                    parts.append(f'{pending_cnt} Pending')
                grid[f'codelab_t{t}'] = ', '.join(parts)
            else:
                grid[f'codelab_t{t}'] = ''

            # Skill Lab
            sl_match = next(
                (s for s in skilllab_map.get(email, [])
                 if s.problem_statement and label.lower() in s.problem_statement.lower()),
                None,
            )
            if sl_match:
                if sl_match.valid:
                    grid[f'skilllab_t{t}'] = 'Valid'
                elif sl_match.remark and sl_match.remark.strip():
                    grid[f'skilllab_t{t}'] = 'Not Valid'
                else:
                    grid[f'skilllab_t{t}'] = 'Pending'
            else:
                grid[f'skilllab_t{t}'] = ''

        result[email] = grid
    return result


@bp.route('/query', methods=['GET'])
@require_page_access('track_progress_query')
def query_users():
    """Return paginated users filtered by track progress grid status."""
    try:
        search = request.args.get('search', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)

        query = UserPIICombined.query

        if search:
            query = query.filter(or_(
                UserPIICombined.name.ilike(f'%{search}%'),
                UserPIICombined.email.ilike(f'%{search}%'),
                UserPIICombined.organization_name.ilike(f'%{search}%'),
            ))

        query = _apply_track_filters(query, request.args)
        query = query.order_by(UserPIICombined.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        emails = [u.email for u in pagination.items]
        grids = _compute_grid_bulk(emails)

        rows = []
        for u in pagination.items:
            rows.append({
                'id': str(u.id),
                'name': u.name,
                'email': u.email,
                'organization': u.organization_name,
                'grid': grids.get(u.email, {}),
            })

        return jsonify({
            'rows': rows,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/stats', methods=['GET'])
@require_page_access('track_progress_query')
def get_stats():
    """Return total count for the current filter set."""
    try:
        search = request.args.get('search', '').strip()
        query = UserPIICombined.query
        if search:
            query = query.filter(or_(
                UserPIICombined.name.ilike(f'%{search}%'),
                UserPIICombined.email.ilike(f'%{search}%'),
                UserPIICombined.organization_name.ilike(f'%{search}%'),
            ))
        query = _apply_track_filters(query, request.args)
        total = query.count()
        return jsonify({'total': total}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/download', methods=['GET'])
@require_page_access('track_progress_query')
def download_csv():
    """Download filtered results as CSV."""
    try:
        search = request.args.get('search', '').strip()
        query = UserPIICombined.query
        if search:
            query = query.filter(or_(
                UserPIICombined.name.ilike(f'%{search}%'),
                UserPIICombined.email.ilike(f'%{search}%'),
                UserPIICombined.organization_name.ilike(f'%{search}%'),
            ))
        query = _apply_track_filters(query, request.args)
        query = query.order_by(UserPIICombined.created_at.desc())
        users = query.all()

        emails = [u.email for u in users]
        grids = _compute_grid_bulk(emails)

        import csv
        buf = io.StringIO()
        writer = csv.writer(buf)

        header = ['Name', 'Email', 'Organization']
        for t in TRACK_NUMBERS:
            header.extend([
                f'Webinar T{t}', f'Optional MCQ T{t}',
                f'Code Lab T{t}', f'Skill Lab T{t}',
            ])
        writer.writerow(header)

        for u in users:
            g = grids.get(u.email, {})
            row = [u.name or '', u.email or '', u.organization_name or '']
            for t in TRACK_NUMBERS:
                row.extend([
                    g.get(f'webinar_t{t}', ''),
                    g.get(f'opt_mcq_t{t}', ''),
                    g.get(f'codelab_t{t}', ''),
                    g.get(f'skilllab_t{t}', ''),
                ])
            writer.writerow(row)

        output = buf.getvalue()
        buf.close()

        return Response(
            output,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=track_progress_query.csv'},
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
