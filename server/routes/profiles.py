"""
User profiles routes (for viewing user_pii data)
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import or_, desc, and_, func, text, case
from server.models import db, UserPIICombined, ActivityLog, SkillboostProfile, CreditLink, SkillLabSubmission, CodeLabSubmission, ProjectSubmission, OptionalMcqResponse, MainMcqResponse
from server.utils.cohort_participant_models import participant_model
from server.utils.auth import get_current_user
from server.utils.permissions import require_role, require_page_access
from server.utils.state_normalize import (
    normalize_state,
    get_state_filter_values,
    distinct_canonical_states,
)
from server.utils.country_normalize import country_filter_or_conditions, distinct_canonical_countries
from server.utils.date_format import format_datetime_utc

bp = Blueprint('profiles', __name__)


@bp.route('', methods=['GET'])
@require_page_access('profiles')
def get_profiles():
    """Get user profiles with search and filters"""
    try:
        PII = participant_model(UserPIICombined)
        SB = participant_model(SkillboostProfile)

        # Get query parameters (support multiple values via getlist for filter dropdowns)
        search = request.args.get('search', '').strip()
        organizations = [x.strip() for x in request.args.getlist('organization') if x and x.strip()]
        domains = [x.strip() for x in request.args.getlist('domain') if x and x.strip()]
        countries = [x.strip() for x in request.args.getlist('country') if x and x.strip()]
        states = [x.strip() for x in request.args.getlist('state') if x and x.strip()]
        cities = [x.strip() for x in request.args.getlist('city') if x and x.strip()]
        genders = [x.strip() for x in request.args.getlist('gender') if x and x.strip()]
        class_streams = [x.strip() for x in request.args.getlist('class_stream') if x and x.strip()]
        designations = [x.strip() for x in request.args.getlist('designation') if x and x.strip()]
        occupations = [x.strip() for x in request.args.getlist('occupation') if x and x.strip()]
        has_github = request.args.get('has_github', '').strip()
        has_linkedin = request.args.get('has_linkedin', '').strip()
        bob_match = request.args.get('bob_match', '').strip()
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)  # Max 100 per page
        
        query = PII.query
        
        if search:
            search_filter = or_(
                PII.name.ilike(f'%{search}%'),
                PII.email.ilike(f'%{search}%'),
                PII.organization_name.ilike(f'%{search}%'),
                PII.designation.ilike(f'%{search}%'),
                PII.occupation.ilike(f'%{search}%')
            )
            query = query.filter(search_filter)
        
        if organizations:
            from server.utils.org_normalize import get_org_filter_conditions
            org_cond = get_org_filter_conditions(PII.organization_name, organizations)
            if org_cond is not None:
                query = query.filter(org_cond)
        
        if domains:
            query = query.filter(or_(*[PII.domain.ilike(f'%{d}%') for d in domains]))
        
        if countries:
            cf = country_filter_or_conditions(PII.country, countries)
            if cf is not None:
                query = query.filter(cf)
        
        if states:
            all_state_values = []
            for state in states:
                state_values = get_state_filter_values(state)
                if state_values:
                    all_state_values.extend(state_values)
                else:
                    all_state_values.append(state)
            if all_state_values:
                query = query.filter(PII.state.in_(all_state_values))
        
        if cities:
            query = query.filter(or_(*[PII.city.ilike(f'%{c}%') for c in cities]))
        
        if genders:
            query = query.filter(or_(*[PII.gender.ilike(f'%{g}%') for g in genders]))
        
        if class_streams:
            query = query.filter(or_(*[PII.class_stream.ilike(f'%{s}%') for s in class_streams]))
        
        if designations:
            query = query.filter(or_(*[PII.designation.ilike(f'%{d}%') for d in designations]))
        
        if occupations:
            query = query.filter(or_(*[PII.occupation.ilike(f'%{o}%') for o in occupations]))
        
        if has_github.lower() == 'true':
            query = query.filter(PII.github_url.isnot(None), PII.github_url != '')
        elif has_github.lower() == 'false':
            query = query.filter(or_(PII.github_url.is_(None), PII.github_url == ''))
        
        if has_linkedin.lower() == 'true':
            query = query.filter(PII.linkedin_url.isnot(None), PII.linkedin_url != '')
        elif has_linkedin.lower() == 'false':
            query = query.filter(or_(PII.linkedin_url.is_(None), PII.linkedin_url == ''))
        
        if bob_match.lower() == 'true':
            query = query.filter(PII.bob_match == True)
        elif bob_match.lower() == 'false':
            query = query.filter(PII.bob_match == False)
        
        pagination = query.order_by(PII.created_at.desc()).paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        profiles = [profile.to_dict() for profile in pagination.items]
        for p in profiles:
            if p.get('state'):
                p['state'] = normalize_state(p['state'])
        emails = [p['email'] for p in profiles]
        skillboost_summary = {}
        if emails:
            try:
                rows = db.session.query(
                    SB.email,
                    func.count(SB.email).label('total'),
                    func.sum(case((SB.valid == True, 1), else_=0)).label('verified'),
                    func.sum(case((
                        and_(SB.valid == False, SB.remarks.isnot(None), SB.remarks != ''),
                        1
                    ), else_=0)).label('failed'),
                ).filter(SB.email.in_(emails)).group_by(SB.email).all()
                for row in rows:
                    verified = int(row.verified or 0)
                    total = int(row.total or 0)
                    failed = int(row.failed or 0)
                    pending = max(0, total - verified - failed)
                    skillboost_summary[row.email] = {
                        'total': total,
                        'verified': verified,
                        'pending': pending,
                        'failed': failed,
                    }
            except Exception:
                pass
        for p in profiles:
            s = skillboost_summary.get(p['email']) or {'total': 0, 'verified': 0, 'pending': 0, 'failed': 0}
            p['skillboost_verification'] = s
        
        return jsonify({
            'profiles': profiles,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/filters', methods=['GET'])
@require_page_access('profiles')
def get_filter_options():
    """Get available filter options for dropdowns."""
    try:
        from server.utils.org_normalize import normalize_org_list
        PII = participant_model(UserPIICombined)

        raw_orgs = db.session.query(PII.organization_name).filter(
            PII.organization_name.isnot(None),
            PII.organization_name != ''
        ).distinct().order_by(PII.organization_name).limit(1000).all()
        organizations = normalize_org_list([o[0] for o in raw_orgs])

        domains = [d[0] for d in db.session.query(PII.domain).filter(
            PII.domain.isnot(None), PII.domain != ''
        ).distinct().order_by(PII.domain).limit(1000).all()]

        raw_countries = [c[0] for c in db.session.query(PII.country).filter(
            PII.country.isnot(None), PII.country != ''
        ).distinct().order_by(PII.country).limit(1000).all()]
        countries = distinct_canonical_countries(raw_countries)

        raw_states = [s[0] for s in db.session.query(PII.state).filter(
            PII.state.isnot(None), PII.state != ''
        ).distinct().order_by(PII.state).limit(1000).all() if s[0]]
        states = distinct_canonical_states(raw_states)

        cities = [c[0] for c in db.session.query(PII.city).filter(
            PII.city.isnot(None), PII.city != ''
        ).distinct().order_by(PII.city).limit(1000).all()]

        genders = [g[0] for g in db.session.query(PII.gender).filter(
            PII.gender.isnot(None), PII.gender != ''
        ).distinct().order_by(PII.gender).limit(100).all()]

        class_streams = [cs[0] for cs in db.session.query(PII.class_stream).filter(
            PII.class_stream.isnot(None), PII.class_stream != ''
        ).distinct().order_by(PII.class_stream).limit(1000).all()]

        designations = [des[0] for des in db.session.query(PII.designation).filter(
            PII.designation.isnot(None), PII.designation != ''
        ).distinct().order_by(PII.designation).limit(1000).all()]

        occupations = [occ[0] for occ in db.session.query(PII.occupation).filter(
            PII.occupation.isnot(None), PII.occupation != ''
        ).distinct().order_by(PII.occupation).limit(1000).all()]

        return jsonify({
            'organizations': organizations,
            'domains': domains,
            'countries': countries,
            'states': states,
            'cities': cities,
            'genders': genders,
            'class_streams': class_streams,
            'designations': designations,
            'occupations': occupations,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/<profile_id>', methods=['GET'])
@require_page_access('profiles')
def get_profile_detail(profile_id):
    """Get detailed profile information including Skill Lab / Skillboost profiles for this user (by email)."""
    try:
        PII = participant_model(UserPIICombined)
        SB = participant_model(SkillboostProfile)
        CL_m = participant_model(CreditLink)
        SL_m = participant_model(SkillLabSubmission)
        CL_sub = participant_model(CodeLabSubmission)
        PS_m = participant_model(ProjectSubmission)
        OMR = participant_model(OptionalMcqResponse)
        MMR = participant_model(MainMcqResponse)

        profile = PII.query.filter_by(id=profile_id).first()
        if not profile:
            return jsonify({'error': 'Profile not found'}), 404
        
        skillboost_profiles = []
        try:
            rows = (
                db.session.query(SB, CL_m)
                .outerjoin(CL_m, SB.credit_link_id == CL_m.id)
                .filter(SB.email == profile.email)
                .order_by(SB.created_at.desc())
            ).all()
            for sp, link in rows:
                d = sp.to_dict()
                d['link_url'] = link.link_url if link else None
                d['link_display_order'] = link.display_order if link else None
                d['allocated_at'] = sp.updated_at.isoformat() if (sp.credit_link_id and sp.updated_at) else None
                skillboost_profiles.append(d)
        except Exception:
            pass
        
        skilllab_submissions = []
        try:
            subs = SL_m.query.filter_by(leader_email=profile.email).all()
            skilllab_submissions = [s.to_dict() for s in subs]
        except Exception:
            pass

        codelab_submissions = []
        try:
            csubs = CL_sub.query.filter_by(leader_email=profile.email).all()
            codelab_submissions = [s.to_dict() for s in csubs]
        except Exception:
            pass

        project_submissions = []
        try:
            email_key = (profile.email or '').strip().lower()
            if email_key:
                psubs = PS_m.query.filter(
                    func.lower(PS_m.leader_email) == email_key
                ).all()
                project_submissions = [s.to_dict() for s in psubs]
        except Exception:
            pass

        optional_mcq_scores = []
        try:
            from server.utils.mcq_answer_key import get_response_score
            email_lower = (profile.email or '').strip().lower()
            if email_lower:
                rows = (
                    OMR.query.filter_by(email=email_lower)
                    .order_by(desc(OMR.created_at), desc(OMR.id))
                    .all()
                )
                for r in rows:
                    auto = get_response_score(r)
                    optional_mcq_scores.append({
                        'id': str(r.id),
                        'track_number': r.track_number,
                        'score': auto['correct_count'],
                        'score_display': auto['score_display'],
                        'created_at': r.created_at.isoformat() if r.created_at else None,
                    })
        except Exception:
            pass

        main_mcq_scores = []
        try:
            email_lower = (profile.email or '').strip().lower()
            if email_lower:
                rows = MMR.query.filter(func.lower(MMR.email) == email_lower).all()
                for r in rows:
                    score = r.score if r.score is not None else 0
                    main_mcq_scores.append({
                        'track_number': r.track_number,
                        'score': score,
                        'score_display': f'{score}/10',
                    })
        except Exception:
            pass

        profile_dict = profile.to_dict()
        if profile_dict.get('state'):
            profile_dict['state'] = normalize_state(profile_dict['state'])
        return jsonify({
            'profile': profile_dict,
            'skillboost_profiles': skillboost_profiles,
            'skilllab_submissions': skilllab_submissions,
            'codelab_submissions': codelab_submissions,
            'project_submissions': project_submissions,
            'optional_mcq_scores': optional_mcq_scores,
            'main_mcq_scores': main_mcq_scores,
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _master_log_to_profile_log(row):
    """Map a master_logs row to the format expected by the profile activity UI."""
    table_name = (getattr(row, 'table_name', None) or '').strip()
    op = (getattr(row, 'operation_type', None) or '').upper()
    if op == 'INSERT':
        action = 'create'
    elif op == 'UPDATE':
        action = 'update'
    elif op == 'DELETE':
        action = 'delete'
    else:
        action = 'create'
    changed_by = getattr(row, 'changed_by', None) or 'system'
    if table_name == 'skillboost_profile':
        if op == 'INSERT':
            summary = f"Skill Lab profile added by {changed_by}"
        elif op == 'UPDATE':
            summary = f"Skill Lab verification updated by {changed_by}"
        else:
            summary = f"Skill Lab profile removed by {changed_by}"
    elif table_name == 'optional_mcq_response':
        if op == 'INSERT':
            summary = f"Optional MCQ response added by {changed_by}"
        elif op == 'UPDATE':
            summary = f"Optional MCQ response updated by {changed_by}"
        else:
            summary = f"Optional MCQ response removed by {changed_by}"
    elif table_name == 'optional_mcq_verification':
        if op == 'INSERT':
            summary = f"Optional MCQ verification added by {changed_by}"
        elif op == 'UPDATE':
            summary = f"Optional MCQ verification updated by {changed_by}"
        else:
            summary = f"Optional MCQ verification removed by {changed_by}"
    else:
        if op == 'INSERT':
            summary = f"Created by {changed_by}"
        elif op == 'UPDATE':
            summary = f"Updated by {changed_by}"
        else:
            summary = f"Deleted by {changed_by}"
    ts = getattr(row, 'timestamp', None)
    created_at = format_datetime_utc(ts)
    changes = []
    old_vals = getattr(row, 'old_values', None)
    new_vals = getattr(row, 'new_values', None)
    if op == 'UPDATE' and old_vals and new_vals:
        old = old_vals if isinstance(old_vals, dict) else {}
        new = new_vals if isinstance(new_vals, dict) else {}
        for key in set(old) | set(new):
            if old.get(key) != new.get(key):
                changes.append({
                    'field': key,
                    'old_value': old.get(key),
                    'new_value': new.get(key),
                })
    return {
        'action': action,
        'created_at': created_at,
        'summary': summary,
        'changes': changes,
        'changed_by': changed_by,
        'table_name': table_name or None,
    }


@bp.route('/<profile_id>/logs', methods=['GET'])
@require_page_access('profiles')
def get_profile_logs(profile_id):
    """Get activity logs for a profile from master_logs (user_pii or user_pii_injected by id + skillboost_profile by email)."""
    try:
        PII = participant_model(UserPIICombined)
        profile = PII.query.filter_by(id=profile_id).first()
        if not profile:
            return jsonify({'error': 'Profile not found'}), 404
        
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        offset = (page - 1) * per_page
        record_id = str(profile_id)
        profile_email = (profile.email or '').strip()
        pii_table = (profile.source or 'user_pii').strip()

        try:
            # master_logs: PII table by id (user_pii or user_pii_injected); skillboost_profile, optional_mcq_* by email
            total = db.session.execute(
                text("""
                    SELECT (
                        (SELECT COUNT(*) FROM master_logs
                         WHERE table_name = :pii_table AND record_identifier = :rid)
                        +
                        (SELECT COUNT(*) FROM master_logs
                         WHERE table_name = 'skillboost_profile'
                           AND (new_values->>'email' = :email OR old_values->>'email' = :email))
                        +
                        (SELECT COUNT(*) FROM master_logs
                         WHERE table_name = 'optional_mcq_response'
                           AND (LOWER(COALESCE(new_values->>'email', '')) = LOWER(:email) OR LOWER(COALESCE(old_values->>'email', '')) = LOWER(:email)))
                        +
                        (SELECT COUNT(*) FROM master_logs
                         WHERE table_name = 'optional_mcq_verification'
                           AND (LOWER(COALESCE(new_values->>'email', '')) = LOWER(:email) OR LOWER(COALESCE(old_values->>'email', '')) = LOWER(:email)))
                    ) AS cnt
                """),
                {"rid": record_id, "email": profile_email, "pii_table": pii_table}
            ).scalar() or 0
            rows = db.session.execute(
                text("""
                    (SELECT log_id, table_name, operation_type, record_identifier,
                            old_values, new_values, changed_by, timestamp, additional_info
                     FROM master_logs
                     WHERE table_name = :pii_table AND record_identifier = :rid)
                    UNION ALL
                    (SELECT log_id, table_name, operation_type, record_identifier,
                            old_values, new_values, changed_by, timestamp, additional_info
                     FROM master_logs
                     WHERE table_name = 'skillboost_profile'
                       AND (new_values->>'email' = :email OR old_values->>'email' = :email))
                    UNION ALL
                    (SELECT log_id, table_name, operation_type, record_identifier,
                            old_values, new_values, changed_by, timestamp, additional_info
                     FROM master_logs
                     WHERE table_name = 'optional_mcq_response'
                       AND (LOWER(COALESCE(new_values->>'email', '')) = LOWER(:email) OR LOWER(COALESCE(old_values->>'email', '')) = LOWER(:email)))
                    UNION ALL
                    (SELECT log_id, table_name, operation_type, record_identifier,
                            old_values, new_values, changed_by, timestamp, additional_info
                     FROM master_logs
                     WHERE table_name = 'optional_mcq_verification'
                       AND (LOWER(COALESCE(new_values->>'email', '')) = LOWER(:email) OR LOWER(COALESCE(old_values->>'email', '')) = LOWER(:email)))
                    ORDER BY timestamp DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"rid": record_id, "email": profile_email, "pii_table": pii_table, "limit": per_page, "offset": offset}
            ).fetchall()
            logs = [_master_log_to_profile_log(row) for row in rows]
            pages = (total + per_page - 1) // per_page if per_page else 0
            return jsonify({
                'logs': logs,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'pages': pages,
                    'has_next': page < pages,
                    'has_prev': page > 1,
                }
            }), 200
        except Exception:
            # Fallback to activity_logs if master_logs not applied
            query = ActivityLog.query.filter(
                ActivityLog.entity_type == pii_table,
                ActivityLog.entity_id == record_id
            ).order_by(ActivityLog.created_at.desc())
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            logs = [log.to_dict() for log in pagination.items]
            return jsonify({
                'logs': logs,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': pagination.total,
                    'pages': pagination.pages,
                    'has_next': pagination.has_next,
                    'has_prev': pagination.has_prev,
                }
            }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
