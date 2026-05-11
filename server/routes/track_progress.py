"""
Track Progress Query page — filter users by their track progress grid status.
Supports filtering by Webinar, Main/Optional MCQ, Code Lab, Project Submission, and Skill Lab per track.
"""
import io
from collections import defaultdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, request, jsonify, Response, current_app
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import load_only, noload, sessionmaker
from server.models import (
    db, UserPIICombined, CodeLabSubmission, SkillLabSubmission, ProjectSubmission, OptionalMcqResponse, MainMcqResponse,
)
from server.utils.cohort_participant_models import participant_model, snapshot_cohort_globals, apply_cohort_globals
from server.utils.auth import get_current_user
from server.utils.permissions import require_page_access

bp = Blueprint('track_progress', __name__)

TRACK_NUMBERS = (1, 2, 3)
TRACK_LABELS = {1: 'Track 1', 2: 'Track 2', 3: 'Track 3'}


def _latest_optional_mcq_for_track(rows, track_num):
    """When multiple Optional MCQ rows exist per email/track (e.g. Cohort 2), use the latest by created_at."""
    opts = [o for o in rows if o.track_number == track_num]
    if not opts:
        return None
    opts.sort(key=lambda o: o.created_at or datetime.min, reverse=True)
    return opts[0]


def _build_codelab_exists(track, extra_filters=None):
    """Return an EXISTS clause for CodeLabSubmission on a given track."""
    CL = participant_model(CodeLabSubmission)
    PII = participant_model(UserPIICombined)
    conditions = [
        func.lower(CL.leader_email) == func.lower(PII.email),
        CL.track_number == track,
    ]
    if extra_filters:
        conditions.extend(extra_filters)
    return db.session.query(CL.id).filter(*conditions).exists()


def _build_skilllab_exists(track, extra_filters=None):
    """Return an EXISTS clause for SkillLabSubmission on a given track (via problem_statement)."""
    label = TRACK_LABELS[track]
    SL = participant_model(SkillLabSubmission)
    PII = participant_model(UserPIICombined)
    conditions = [
        func.lower(SL.leader_email) == func.lower(PII.email),
        SL.problem_statement.ilike(f'%{label}%'),
    ]
    if extra_filters:
        conditions.extend(extra_filters)
    return db.session.query(SL.id).filter(*conditions).exists()


def _build_optmcq_exists(track, extra_filters=None):
    """Return an EXISTS clause for OptionalMcqResponse on a given track."""
    OMR = participant_model(OptionalMcqResponse)
    PII = participant_model(UserPIICombined)
    conditions = [
        func.lower(OMR.email) == func.lower(PII.email),
        OMR.track_number == track,
    ]
    if extra_filters:
        conditions.extend(extra_filters)
    return db.session.query(OMR.id).filter(*conditions).exists()


def _build_mainmcq_exists(track, extra_filters=None):
    """Return an EXISTS clause for MainMcqResponse on a given track."""
    MMR = participant_model(MainMcqResponse)
    PII = participant_model(UserPIICombined)
    conditions = [
        func.lower(MMR.email) == func.lower(PII.email),
        MMR.track_number == track,
    ]
    if extra_filters:
        conditions.extend(extra_filters)
    return db.session.query(MMR.id).filter(*conditions).exists()


def _build_project_exists(track, extra_filters=None):
    """Return an EXISTS clause for ProjectSubmission on a given track (leader_email ↔ profile email)."""
    PS = participant_model(ProjectSubmission)
    PII = participant_model(UserPIICombined)
    conditions = [
        func.lower(PS.leader_email) == func.lower(PII.email),
        PS.track_number == track,
    ]
    if extra_filters:
        conditions.extend(extra_filters)
    return db.session.query(PS.id).filter(*conditions).exists()


def _combo_track_active(args, t: int) -> bool:
    """Shortcut preset: (Main MCQ submitted OR Project submitted OR Skill Lab submitted) AND Code Lab not submitted."""
    v = (args.get(f'combo_t{t}', '') or '').strip().lower()
    return v in ('1', 'true', 'yes')


def _apply_track_filters(query, args):
    """Parse track-progress filter params and append WHERE conditions to the query."""
    for t in TRACK_NUMBERS:
        combo = _combo_track_active(args, t)

        # Webinar / Optional MCQ: skip for this track when combo preset is on — they often
        # imply code-lab state (e.g. webinar Valid = has code lab) and contradict
        # (MCQ|Project|Skill) AND NOT code lab.
        if not combo:
            # --- Webinar (derived from codelab existence) ---
            val = args.get(f'webinar_t{t}', '').strip().lower()
            if val == 'valid' or val == 'submitted':
                query = query.filter(_build_codelab_exists(t))
            elif val == 'empty':
                query = query.filter(~_build_codelab_exists(t))

        # --- Optional MCQ ---
        val = args.get(f'opt_mcq_t{t}', '').strip().lower()
        OMR = participant_model(OptionalMcqResponse)
        if val == 'pass':
            query = query.filter(_build_optmcq_exists(t, [OMR.score >= 6]))
        elif val == 'fail':
            query = query.filter(_build_optmcq_exists(t, [OMR.score < 6]))
        elif val == 'submitted':
            query = query.filter(_build_optmcq_exists(t))
        elif val == 'empty':
            query = query.filter(~_build_optmcq_exists(t))

        # --- Preset: (Main MCQ OR Project OR Skill Lab) for this track AND no code lab for this track ---
        if combo:
            query = query.filter(
                and_(
                    or_(
                        _build_mainmcq_exists(t),
                        _build_project_exists(t),
                        _build_skilllab_exists(t),
                    ),
                    ~_build_codelab_exists(t),
                )
            )
            continue

        # --- Main MCQ ---
        val = args.get(f'main_mcq_t{t}', '').strip().lower()
        MMR = participant_model(MainMcqResponse)
        if val == 'pass':
            query = query.filter(_build_mainmcq_exists(t, [MMR.score >= 6]))
        elif val == 'fail':
            query = query.filter(_build_mainmcq_exists(t, [MMR.score < 6]))
        elif val == 'submitted':
            query = query.filter(_build_mainmcq_exists(t))
        elif val == 'empty':
            query = query.filter(~_build_mainmcq_exists(t))

        # --- Code Lab ---
        val = args.get(f'codelab_t{t}', '').strip().lower()
        CL = participant_model(CodeLabSubmission)
        if val == 'valid':
            query = query.filter(_build_codelab_exists(t, [CL.valid == True]))
        elif val == 'not_valid':
            query = query.filter(_build_codelab_exists(t, [
                CL.valid == False,
                CL.remark.isnot(None),
                CL.remark != '',
            ]))
        elif val == 'pending':
            query = query.filter(_build_codelab_exists(t, [
                CL.valid == False,
                or_(CL.remark.is_(None), CL.remark == ''),
            ]))
        elif val == 'submitted':
            query = query.filter(_build_codelab_exists(t))
        elif val == 'empty':
            query = query.filter(~_build_codelab_exists(t))

        # --- Skill Lab ---
        val = args.get(f'skilllab_t{t}', '').strip().lower()
        SL = participant_model(SkillLabSubmission)
        if val == 'valid':
            query = query.filter(_build_skilllab_exists(t, [SL.valid == True]))
        elif val == 'not_valid':
            query = query.filter(_build_skilllab_exists(t, [
                SL.valid == False,
                SL.remark.isnot(None),
                SL.remark != '',
            ]))
        elif val == 'pending':
            query = query.filter(_build_skilllab_exists(t, [
                SL.valid == False,
                or_(SL.remark.is_(None), SL.remark == ''),
            ]))
        elif val == 'submitted':
            query = query.filter(_build_skilllab_exists(t))
        elif val == 'empty':
            query = query.filter(~_build_skilllab_exists(t))

        # --- Project Submission (per track_number 1–3) ---
        val = args.get(f'project_t{t}', '').strip().lower()
        PS = participant_model(ProjectSubmission)
        if val == 'valid':
            query = query.filter(_build_project_exists(t, [PS.valid == True]))
        elif val == 'not_valid':
            query = query.filter(_build_project_exists(t, [
                PS.valid == False,
                PS.remark.isnot(None),
                PS.remark != '',
            ]))
        elif val == 'pending':
            query = query.filter(_build_project_exists(t, [
                PS.valid == False,
                or_(PS.remark.is_(None), PS.remark == ''),
            ]))
        elif val == 'submitted':
            query = query.filter(_build_project_exists(t))
        elif val == 'empty':
            query = query.filter(~_build_project_exists(t))

    return query


def _track_progress_base_query(session, search: str, filter_args):
    """Filtered UserPIICombined query (session-bound for parallel workers)."""
    PII = participant_model(UserPIICombined)
    query = session.query(PII).options(
        load_only(
            PII.id,
            PII.name,
            PII.email,
            PII.organization_name,
            PII.mobile_number,
            PII.registered_at,
            PII.created_at,
        )
    )
    if search:
        query = query.filter(or_(
            PII.name.ilike(f'%{search}%'),
            PII.email.ilike(f'%{search}%'),
            PII.organization_name.ilike(f'%{search}%'),
        ))
    query = _apply_track_filters(query, filter_args)
    return query


def _compute_grid_bulk(emails):
    """Bulk-compute the track progress grid for a list of emails.
    Returns {email: {webinar_t1: '...', codelab_t1: '...', ...}} .

    Uses load_only + noload(leader/participant) so we do not JOIN user_pii on every row
    (models default to lazy='joined' on those relationships).
    """
    if not emails:
        return {}

    def _norm(e):
        return (e or '').strip().lower()

    # Resolve cohort-specific models at call time (within request context)
    CL = participant_model(CodeLabSubmission)
    SL = participant_model(SkillLabSubmission)
    OMR = participant_model(OptionalMcqResponse)
    MMR = participant_model(MainMcqResponse)
    PS = participant_model(ProjectSubmission)

    _cl_opts = (load_only(CL.leader_email, CL.track_number, CL.valid, CL.remark),)
    _sl_opts = (load_only(SL.leader_email, SL.problem_statement, SL.valid, SL.remark),)
    _opt_opts = (load_only(OMR.email, OMR.track_number, OMR.score),)
    _main_opts = (load_only(MMR.email, MMR.track_number, MMR.score),)
    _proj_opts = (load_only(PS.leader_email, PS.track_number, PS.valid, PS.remark),)

    lowered = list({_norm(e) for e in emails}) if emails else []

    codelab_map = defaultdict(list)
    skilllab_map = defaultdict(list)
    optmcq_map = defaultdict(list)
    mainmcq_map = defaultdict(list)
    project_map = defaultdict(list)

    if lowered:
        engine = db.engine
        app = current_app._get_current_object()
        Maker = sessionmaker(bind=engine, expire_on_commit=False)
        cohort_snap = snapshot_cohort_globals()
        # Large IN lists (e.g. CSV of many users) are slower to plan; chunk batches.
        batch_size = 800
        batches = (
            [lowered]
            if len(lowered) <= batch_size
            else [lowered[i : i + batch_size] for i in range(0, len(lowered), batch_size)]
        )

        for batch in batches:

            def _pull_codelab(batch=batch, snap=cohort_snap):
                with app.app_context():
                    apply_cohort_globals(snap[0], snap[1])
                    _CL = participant_model(CodeLabSubmission)
                    s = Maker()
                    try:
                        return s.query(_CL).options(*_cl_opts).filter(
                            func.lower(_CL.leader_email).in_(batch)
                        ).all()
                    finally:
                        s.close()

            def _pull_skilllab(batch=batch, snap=cohort_snap):
                with app.app_context():
                    apply_cohort_globals(snap[0], snap[1])
                    _SL = participant_model(SkillLabSubmission)
                    s = Maker()
                    try:
                        return s.query(_SL).options(*_sl_opts).filter(
                            func.lower(_SL.leader_email).in_(batch)
                        ).all()
                    finally:
                        s.close()

            def _pull_optmcq(batch=batch, snap=cohort_snap):
                with app.app_context():
                    apply_cohort_globals(snap[0], snap[1])
                    _OMR = participant_model(OptionalMcqResponse)
                    s = Maker()
                    try:
                        return s.query(_OMR).options(*_opt_opts).filter(
                            func.lower(_OMR.email).in_(batch)
                        ).all()
                    finally:
                        s.close()

            def _pull_mainmcq(batch=batch, snap=cohort_snap):
                with app.app_context():
                    apply_cohort_globals(snap[0], snap[1])
                    _MMR = participant_model(MainMcqResponse)
                    s = Maker()
                    try:
                        return s.query(_MMR).options(*_main_opts).filter(
                            func.lower(_MMR.email).in_(batch)
                        ).all()
                    finally:
                        s.close()

            def _pull_project(batch=batch, snap=cohort_snap):
                with app.app_context():
                    apply_cohort_globals(snap[0], snap[1])
                    _PS = participant_model(ProjectSubmission)
                    s = Maker()
                    try:
                        return s.query(_PS).options(*_proj_opts).filter(
                            func.lower(_PS.leader_email).in_(batch)
                        ).all()
                    finally:
                        s.close()

            with ThreadPoolExecutor(max_workers=5) as ex:
                f_cl = ex.submit(_pull_codelab)
                f_sl = ex.submit(_pull_skilllab)
                f_opt = ex.submit(_pull_optmcq)
                f_main = ex.submit(_pull_mainmcq)
                f_proj = ex.submit(_pull_project)
                for c in f_cl.result():
                    codelab_map[_norm(c.leader_email)].append(c)
                for srow in f_sl.result():
                    skilllab_map[_norm(srow.leader_email)].append(srow)
                for o in f_opt.result():
                    optmcq_map[_norm(o.email)].append(o)
                for m in f_main.result():
                    mainmcq_map[_norm(m.email)].append(m)
                for p in f_proj.result():
                    project_map[_norm(p.leader_email)].append(p)

    result = {}
    for email in emails:
        email_key = _norm(email)
        grid = {}
        for t in TRACK_NUMBERS:
            label = TRACK_LABELS[t]

            # Webinar: mark Valid for this track when user has submitted code lab for this track (same as Track 1)
            has_codelab = any(c.track_number == t for c in codelab_map.get(email_key, []))
            grid[f'webinar_t{t}'] = 'Valid' if has_codelab else ''

            # Optional MCQ — Verified when score >= 6 (latest submission if multiple)
            mcq_match = _latest_optional_mcq_for_track(optmcq_map.get(email_key, []), t)
            if mcq_match:
                score = mcq_match.score if mcq_match.score is not None else 0
                grid[f'opt_mcq_t{t}'] = 'Verified' if score >= 6 else 'Fail'
            else:
                grid[f'opt_mcq_t{t}'] = ''

            # Main MCQ — Verified when score >= 6
            main_mcq_match = next((m for m in mainmcq_map.get(email_key, []) if m.track_number == t), None)
            if main_mcq_match:
                score = main_mcq_match.score if main_mcq_match.score is not None else 0
                grid[f'main_mcq_t{t}'] = 'Verified' if score >= 6 else 'Fail'
            else:
                grid[f'main_mcq_t{t}'] = ''

            # Code Lab
            cl_matches = [c for c in codelab_map.get(email_key, []) if c.track_number == t]
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
                (s for s in skilllab_map.get(email_key, [])
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

            # Project Submission (one row per email per track)
            ps_match = next(
                (p for p in project_map.get(email_key, []) if p.track_number == t),
                None,
            )
            if ps_match:
                if ps_match.valid:
                    grid[f'project_t{t}'] = 'Valid'
                elif ps_match.remark and ps_match.remark.strip():
                    grid[f'project_t{t}'] = 'Not Valid'
                else:
                    grid[f'project_t{t}'] = 'Pending'
            else:
                grid[f'project_t{t}'] = ''

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
        filter_args = request.args
        engine = db.engine
        app = current_app._get_current_object()
        Maker = sessionmaker(bind=engine, expire_on_commit=False)

        cohort_snap = snapshot_cohort_globals()

        def _fetch_page_rows(snap=cohort_snap):
            with app.app_context():
                apply_cohort_globals(snap[0], snap[1])
                PII = participant_model(UserPIICombined)
                s = Maker()
                try:
                    q = _track_progress_base_query(s, search, filter_args)
                    return q.order_by(PII.created_at.desc()).offset(
                        (page - 1) * per_page
                    ).limit(per_page).all()
                finally:
                    s.close()

        def _fetch_total(snap=cohort_snap):
            with app.app_context():
                apply_cohort_globals(snap[0], snap[1])
                s = Maker()
                try:
                    q = _track_progress_base_query(s, search, filter_args)
                    return q.order_by(None).count()
                finally:
                    s.close()

        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_items = ex.submit(_fetch_page_rows)
            fut_total = ex.submit(_fetch_total)
            items = fut_items.result()
            total = fut_total.result()

        pages = (total + per_page - 1) // per_page if per_page else 0
        emails = [u.email for u in items]
        grids = _compute_grid_bulk(emails)

        rows = []
        for u in items:
            rows.append({
                'id': str(u.id),
                'name': u.name,
                'email': u.email,
                'organization': u.organization_name,
                'grid': grids.get(u.email, {}),
            })

        return jsonify({
            'rows': rows,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': pages,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/stats', methods=['GET'])
@require_page_access('track_progress_query')
def get_stats():
    """Return total count for the current filter set."""
    try:
        search = request.args.get('search', '').strip()
        q = _track_progress_base_query(db.session, search, request.args)
        total = q.order_by(None).count()
        return jsonify({'total': total}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/download', methods=['GET'])
@require_page_access('track_progress_query')
def download_csv():
    """Download filtered results as CSV."""
    try:
        search = request.args.get('search', '').strip()
        query = _track_progress_base_query(db.session, search, request.args)
        PII = participant_model(UserPIICombined)
        query = query.order_by(PII.created_at.desc())
        users = query.all()

        emails = [u.email for u in users]
        grids = _compute_grid_bulk(emails)

        import csv
        buf = io.StringIO()
        writer = csv.writer(buf)

        header = ['Name', 'Email', 'Phone', 'Organization', 'Registered At']
        for t in TRACK_NUMBERS:
            header.extend([
                f'Webinar T{t}', f'MCQ T{t}', f'Optional MCQ T{t}',
                f'Code Lab T{t}', f'Project T{t}', f'Skill Lab T{t}',
            ])
        writer.writerow(header)

        for u in users:
            g = grids.get(u.email, {})
            reg_at = u.registered_at.isoformat() if u.registered_at else ''
            row = [u.name or '', u.email or '', u.mobile_number or '', u.organization_name or '', reg_at]
            for t in TRACK_NUMBERS:
                row.extend([
                    g.get(f'webinar_t{t}', ''),
                    g.get(f'main_mcq_t{t}', ''),
                    g.get(f'opt_mcq_t{t}', ''),
                    g.get(f'codelab_t{t}', ''),
                    g.get(f'project_t{t}', ''),
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

