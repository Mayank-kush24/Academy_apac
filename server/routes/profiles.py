"""
User profiles routes (for viewing user_pii data)
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import or_, and_, func, text, case
from server.models import db, UserPIICombined, ActivityLog, SkillboostProfile, CreditLink, SkillLabSubmission, CodeLabSubmission, OptionalMcqResponse
from server.utils.auth import get_current_user
from server.utils.permissions import require_role, require_page_access
from server.utils.state_normalize import (
    normalize_state,
    get_state_filter_values,
    distinct_canonical_states,
)
from server.utils.date_format import format_datetime_utc

bp = Blueprint('profiles', __name__)


@bp.route('', methods=['GET'])
@require_page_access('profiles')
def get_profiles():
    """Get user profiles with search and filters"""
    try:
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
        
        # Start building query (combined: user_pii + user_pii_injected, no duplicate emails)
        query = UserPIICombined.query
        
        # Search filter (searches in name, email, organization)
        if search:
            search_filter = or_(
                UserPIICombined.name.ilike(f'%{search}%'),
                UserPIICombined.email.ilike(f'%{search}%'),
                UserPIICombined.organization_name.ilike(f'%{search}%'),
                UserPIICombined.designation.ilike(f'%{search}%'),
                UserPIICombined.occupation.ilike(f'%{search}%')
            )
            query = query.filter(search_filter)
        
        # Organization filter (multiple allowed)
        if organizations:
            query = query.filter(or_(*[UserPIICombined.organization_name.ilike(f'%{o}%') for o in organizations]))
        
        # Domain filter (multiple allowed)
        if domains:
            query = query.filter(or_(*[UserPIICombined.domain.ilike(f'%{d}%') for d in domains]))
        
        # Country filter (multiple allowed)
        if countries:
            query = query.filter(or_(*[UserPIICombined.country.ilike(f'%{c}%') for c in countries]))
        
        # State filter (multiple allowed; match canonical + all mapped variants per selection)
        if states:
            all_state_values = []
            for state in states:
                state_values = get_state_filter_values(state)
                if state_values:
                    all_state_values.extend(state_values)
                else:
                    all_state_values.append(state)
            if all_state_values:
                query = query.filter(UserPIICombined.state.in_(all_state_values))
        
        # City filter (multiple allowed)
        if cities:
            query = query.filter(or_(*[UserPIICombined.city.ilike(f'%{c}%') for c in cities]))
        
        # Gender filter (multiple allowed)
        if genders:
            query = query.filter(or_(*[UserPIICombined.gender.ilike(f'%{g}%') for g in genders]))
        
        # Class stream filter (multiple allowed)
        if class_streams:
            query = query.filter(or_(*[UserPIICombined.class_stream.ilike(f'%{s}%') for s in class_streams]))
        
        # Designation filter (multiple allowed)
        if designations:
            query = query.filter(or_(*[UserPIICombined.designation.ilike(f'%{d}%') for d in designations]))
        
        # Occupation filter (multiple allowed)
        if occupations:
            query = query.filter(or_(*[UserPIICombined.occupation.ilike(f'%{o}%') for o in occupations]))
        
        # GitHub filter
        if has_github.lower() == 'true':
            query = query.filter(
                UserPIICombined.github_url.isnot(None),
                UserPIICombined.github_url != ''
            )
        elif has_github.lower() == 'false':
            query = query.filter(
                or_(
                    UserPIICombined.github_url.is_(None),
                    UserPIICombined.github_url == ''
                )
            )
        
        # LinkedIn filter
        if has_linkedin.lower() == 'true':
            query = query.filter(
                UserPIICombined.linkedin_url.isnot(None),
                UserPIICombined.linkedin_url != ''
            )
        elif has_linkedin.lower() == 'false':
            query = query.filter(
                or_(
                    UserPIICombined.linkedin_url.is_(None),
                    UserPIICombined.linkedin_url == ''
                )
            )
        
        # BOB match filter (Book of Business)
        if bob_match.lower() == 'true':
            query = query.filter(UserPIICombined.bob_match == True)
        elif bob_match.lower() == 'false':
            query = query.filter(UserPIICombined.bob_match == False)
        
        # Apply pagination (Flask-SQLAlchemy computes total via paginate())
        pagination = query.order_by(UserPIICombined.created_at.desc()).paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        profiles = [profile.to_dict() for profile in pagination.items]
        for p in profiles:
            if p.get('state'):
                p['state'] = normalize_state(p['state'])
        emails = [p['email'] for p in profiles]
        # Skill Lab verification summary per email (total, verified, pending, failed)
        skillboost_summary = {}
        if emails:
            try:
                rows = db.session.query(
                    SkillboostProfile.email,
                    func.count(SkillboostProfile.email).label('total'),
                    func.sum(case((SkillboostProfile.valid == True, 1), else_=0)).label('verified'),
                    func.sum(case((
                        and_(SkillboostProfile.valid == False, SkillboostProfile.remarks.isnot(None), SkillboostProfile.remarks != ''),
                        1
                    ), else_=0)).label('failed'),
                ).filter(SkillboostProfile.email.in_(emails)).group_by(SkillboostProfile.email).all()
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
    """Get available filter options for dropdowns (cached)"""
    from server.utils.cache import cache_result
    
    @cache_result(ttl=600)  # Cache for 10 minutes
    def _get_filter_options():
        """Internal function to fetch filter options"""
        # Get distinct values for filters - limit to top 1000 for performance
        organizations = db.session.query(UserPIICombined.organization_name).filter(
            UserPIICombined.organization_name.isnot(None),
            UserPIICombined.organization_name != ''
        ).distinct().order_by(UserPIICombined.organization_name).limit(1000).all()
        
        domains = db.session.query(UserPIICombined.domain).filter(
            UserPIICombined.domain.isnot(None),
            UserPIICombined.domain != ''
        ).distinct().order_by(UserPIICombined.domain).limit(1000).all()
        
        countries = db.session.query(UserPIICombined.country).filter(
            UserPIICombined.country.isnot(None),
            UserPIICombined.country != ''
        ).distinct().order_by(UserPIICombined.country).limit(1000).all()
        
        raw_states = [s[0] for s in db.session.query(UserPIICombined.state).filter(
            UserPIICombined.state.isnot(None),
            UserPIICombined.state != ''
        ).distinct().order_by(UserPIICombined.state).limit(1000).all() if s[0]]
        states = distinct_canonical_states(raw_states)
        
        cities = db.session.query(UserPIICombined.city).filter(
            UserPIICombined.city.isnot(None),
            UserPIICombined.city != ''
        ).distinct().order_by(UserPIICombined.city).limit(1000).all()
        
        genders = db.session.query(UserPIICombined.gender).filter(
            UserPIICombined.gender.isnot(None),
            UserPIICombined.gender != ''
        ).distinct().order_by(UserPIICombined.gender).limit(100).all()
        
        class_streams = db.session.query(UserPIICombined.class_stream).filter(
            UserPIICombined.class_stream.isnot(None),
            UserPIICombined.class_stream != ''
        ).distinct().order_by(UserPIICombined.class_stream).limit(1000).all()
        
        designations = db.session.query(UserPIICombined.designation).filter(
            UserPIICombined.designation.isnot(None),
            UserPIICombined.designation != ''
        ).distinct().order_by(UserPIICombined.designation).limit(1000).all()
        
        occupations = db.session.query(UserPIICombined.occupation).filter(
            UserPIICombined.occupation.isnot(None),
            UserPIICombined.occupation != ''
        ).distinct().order_by(UserPIICombined.occupation).limit(1000).all()
        
        return {
            'organizations': [o[0] for o in organizations],
            'domains': [d[0] for d in domains],
            'countries': [c[0] for c in countries],
            'states': states,
            'cities': [c[0] for c in cities],
            'genders': [g[0] for g in genders],
            'class_streams': [cs[0] for cs in class_streams],
            'designations': [des[0] for des in designations],
            'occupations': [occ[0] for occ in occupations]
        }
    
    try:
        result = _get_filter_options()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/<profile_id>', methods=['GET'])
@require_page_access('profiles')
def get_profile_detail(profile_id):
    """Get detailed profile information including Skill Lab / Skillboost profiles for this user (by email)."""
    try:
        profile = UserPIICombined.query.filter_by(id=profile_id).first()
        if not profile:
            return jsonify({'error': 'Profile not found'}), 404
        
        # Skill Lab / Skillboost profiles for this user (by email), with credit link info
        skillboost_profiles = []
        try:
            rows = (
                db.session.query(SkillboostProfile, CreditLink)
                .outerjoin(CreditLink, SkillboostProfile.credit_link_id == CreditLink.id)
                .filter(SkillboostProfile.email == profile.email)
                .order_by(SkillboostProfile.created_at.desc())
            ).all()
            for sp, link in rows:
                d = sp.to_dict()
                d['link_url'] = link.link_url if link else None
                d['link_display_order'] = link.display_order if link else None
                d['allocated_at'] = sp.updated_at.isoformat() if (sp.credit_link_id and sp.updated_at) else None
                skillboost_profiles.append(d)
        except Exception:
            pass
        
        # Skill Lab submissions for this user (by email)
        skilllab_submissions = []
        try:
            subs = SkillLabSubmission.query.filter_by(leader_email=profile.email).all()
            skilllab_submissions = [s.to_dict() for s in subs]
        except Exception:
            pass

        # Code Lab submissions for this user (by email)
        codelab_submissions = []
        try:
            csubs = CodeLabSubmission.query.filter_by(leader_email=profile.email).all()
            codelab_submissions = [s.to_dict() for s in csubs]
        except Exception:
            pass

        # Optional MCQ scores per track (same marking as Optional MCQ Verification page: 6+ = pass)
        optional_mcq_scores = []
        try:
            from server.utils.mcq_answer_key import get_response_score
            email_lower = (profile.email or '').strip().lower()
            if email_lower:
                rows = OptionalMcqResponse.query.filter_by(email=email_lower).all()
                for r in rows:
                    auto = get_response_score(r)
                    optional_mcq_scores.append({
                        'track_number': r.track_number,
                        'score': auto['correct_count'],
                        'score_display': auto['score_display'],
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
            'optional_mcq_scores': optional_mcq_scores,
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
        profile = UserPIICombined.query.filter_by(id=profile_id).first()
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
