"""
Dashboard analytics routes
"""
from flask import Blueprint, jsonify, request
from sqlalchemy import func, desc, case, or_, and_
from datetime import datetime, timedelta, date
from server.models import db, UserPIICombined, SkillboostProfile, SkillLabSubmission, CodeLabSubmission, OptionalMcqResponse
from server.utils.auth import get_current_user
from server.utils.mcq_answer_key import score_submission, get_response_score
from server.utils.permissions import require_page_access
from server.utils.cache import cache_result
from server.utils.state_normalize import normalize_state

bp = Blueprint('dashboard', __name__)

# Module-level cached combined dashboard (summary + charts) - one cache entry per period
@cache_result(ttl=300)
def _get_dashboard_data_cached(period):
    """Fetch summary and charts in one go; cached for 5 min."""
    summary = _fetch_summary_data(period)
    charts = _fetch_charts_data(period, summary=summary)
    return {'summary': summary, 'charts': charts}


@bp.route('/data', methods=['GET'])
@require_page_access('dashboard')
def get_dashboard_data():
    """Combined dashboard summary + charts (single request, cached)."""
    try:
        period = request.args.get('period', 'all')
        result = _get_dashboard_data_cached(period)
        return jsonify(result), 200
    except Exception:
        return jsonify({
            'summary': {
                'total_users': 0, 'apac_except_india_users': 0, 'top_india_state': 'N/A',
                'top_india_city': 'N/A', 'top_india_state_count': None, 'top_india_city_count': None, 'top_india_location_count': None, 'top_apac_country': 'N/A',
                'top_apac_country_count': None,
                'sea_registrations': 0, 'sea_top_country': 'N/A',
                'anz_registrations': 0, 'anz_top_country': 'N/A',
                'east_asia_registrations': 0, 'east_asia_top_country': 'N/A',
                'india_registrations': 0
            },
            'charts': {
                'registration_trends': [], 'gender_distribution': [],
                'registration_source_bifurcation': [{'label': 'Google', 'value': 0}, {'label': 'Outreach', 'value': 0}, {'label': 'Marketing', 'value': 0}, {'label': 'Ads', 'value': 0}, {'label': 'Hack2skill', 'value': 0}, {'label': 'Other', 'value': 0}],
                'occupation_distribution': [], 'top_domains': [], 'top_cities': [], 'top_cities_outside_india': [], 'top_organizations': [],
                'india_state_registrations': [], 'apac_country_registrations': []
            }
        }), 200


@bp.route('/summary', methods=['GET'])
@require_page_access('dashboard')
def get_summary():
    """Get dashboard summary statistics. Prefer GET /data for single round-trip + cache."""
    try:
        period = request.args.get('period', 'all')
        result = _fetch_summary_data(period)
        return jsonify(result), 200
    except Exception:
        return jsonify({
            'total_users': 0, 'unique_organizations': 0, 'top_domain': 'N/A', 'top_city': 'N/A',
            'average_age': None, 'apac_except_india_users': 0, 'top_india_state': 'N/A',
            'top_india_city': 'N/A', 'top_apac_country': 'N/A',
            'sea_registrations': 0, 'sea_top_country': 'N/A',
            'anz_registrations': 0, 'anz_top_country': 'N/A',
            'east_asia_registrations': 0, 'east_asia_top_country': 'N/A',
            'india_registrations': 0
        }), 200


@cache_result(ttl=300)
def _get_region_breakdown_cached(region, period):
    """Cached region breakdown data (5 min)."""
    cutoff_date = _get_period_dates(period)
    date_cond = _date_filter_condition(cutoff_date)
    SEA_COUNTRIES = [
        'Brunei', 'Cambodia', 'Indonesia', 'Laos', 'Malaysia', 'Myanmar',
        'Philippines', 'Singapore', 'Thailand', 'Timor-Leste', 'Vietnam'
    ]
    ANZ_COUNTRIES = ['Australia', 'New Zealand']
    EAST_ASIA_COUNTRIES = [
        'China', 'Hong Kong', 'Japan', 'South Korea', 'North Korea',
        'Taiwan', 'Mongolia'
    ]
    if region == 'india':
        label = 'India'
        q = db.session.query(
            UserPIICombined.state,
            func.count(UserPIICombined.id).label('count')
        ).filter(
            UserPIICombined.country.isnot(None),
            UserPIICombined.country != '',
            UserPIICombined.country.ilike('%India%'),
            UserPIICombined.state.isnot(None),
            UserPIICombined.state != ''
        )
        if date_cond is not None:
            q = q.filter(date_cond)
        rows = q.group_by(UserPIICombined.state).order_by(desc('count')).all()
        from collections import defaultdict
        merged = defaultdict(int)
        for r in rows:
            canonical = normalize_state(r[0]) if r[0] else 'Unknown'
            merged[canonical] += r[1]
        items = [{'name': k, 'count': v} for k, v in sorted(merged.items(), key=lambda x: -x[1])]
    else:
        if region == 'sea':
            label = 'SEA (Southeast Asia)'
            countries = SEA_COUNTRIES
        elif region == 'anz':
            label = 'ANZ (Australia & New Zealand)'
            countries = ANZ_COUNTRIES
        else:
            label = 'Greater China and Korea'
            countries = EAST_ASIA_COUNTRIES
        conds = [UserPIICombined.country.ilike(f'%{c}%') for c in countries]
        q = db.session.query(
            UserPIICombined.country,
            func.count(UserPIICombined.id).label('count')
        ).filter(
            UserPIICombined.country.isnot(None),
            UserPIICombined.country != '',
            or_(*conds)
        )
        if date_cond is not None:
            q = q.filter(date_cond)
        rows = q.group_by(UserPIICombined.country).order_by(desc('count')).all()
        items = [{'name': r[0] or 'Unknown', 'count': r[1]} for r in rows]
    total = sum(i['count'] for i in items)
    return {'region': region, 'label': label, 'items': items, 'total': total}


@bp.route('/region-breakdown', methods=['GET'])
@require_page_access('dashboard')
def get_region_breakdown():
    """Get per-country (or per-state for India) registration counts for a region (cached 5 min)."""
    region = (request.args.get('region') or '').strip().lower()
    period = request.args.get('period', 'all')
    if region not in ('sea', 'anz', 'east_asia', 'india'):
        return jsonify({'error': 'Invalid region'}), 400
    try:
        data = _get_region_breakdown_cached(region, period)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _get_period_dates(period):
    """Return cutoff_date for the given period.
    For 'all': no filter (entire dataset).
    For 'month': start of current calendar month (1st at 00:00:00).
    For 7d/30d/90d: that many days ago from now.
    """
    cutoff_date = None
    if period == 'all':
        return None
    if period == 'month':
        # Current calendar month: from 1st of this month 00:00:00
        now = datetime.now()
        cutoff_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == '7d':
        cutoff_date = datetime.now() - timedelta(days=7)
    elif period == '30d':
        cutoff_date = datetime.now() - timedelta(days=30)
    elif period == '90d':
        cutoff_date = datetime.now() - timedelta(days=90)
    return cutoff_date


def _date_filter_condition(cutoff_date):
    """Return SQLAlchemy filter for registered_at or created_at >= cutoff_date."""
    if not cutoff_date:
        return None
    return or_(
        and_(UserPIICombined.registered_at.isnot(None), UserPIICombined.registered_at >= cutoff_date),
        and_(UserPIICombined.registered_at.is_(None), UserPIICombined.created_at >= cutoff_date)
    )


def _get_previous_period_range(period):
    """Return (prev_start, current_start) for the previous period (for week-on-week / period-on-period).
    Previous period is the same length as current, immediately before it.
    For 'all' there is no previous period.
    """
    if period == 'all':
        return None, None
    now = datetime.now()
    if period == 'month':
        current_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # First day of last month
        if now.month == 1:
            prev_start = now.replace(year=now.year - 1, month=12, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            prev_start = now.replace(month=now.month - 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return prev_start, current_start
    if period == '7d':
        current_start = now - timedelta(days=7)
        prev_start = now - timedelta(days=14)
        return prev_start, current_start
    if period == '30d':
        current_start = now - timedelta(days=30)
        prev_start = now - timedelta(days=60)
        return prev_start, current_start
    if period == '90d':
        current_start = now - timedelta(days=90)
        prev_start = now - timedelta(days=180)
        return prev_start, current_start
    return None, None


def _previous_period_filter(prev_start, current_start):
    """Filter: registered_at (or created_at) >= prev_start AND < current_start."""
    if prev_start is None or current_start is None:
        return None
    return or_(
        and_(
            UserPIICombined.registered_at.isnot(None),
            UserPIICombined.registered_at >= prev_start,
            UserPIICombined.registered_at < current_start
        ),
        and_(
            UserPIICombined.registered_at.is_(None),
            UserPIICombined.created_at >= prev_start,
            UserPIICombined.created_at < current_start
        )
    )


def _fetch_summary_data(period):
    """Internal function to fetch summary data. period: 'all', 'month', '7d', '30d', '90d'."""
    try:
        cutoff_date = _get_period_dates(period)
        date_cond = _date_filter_condition(cutoff_date)
        
        base_query = UserPIICombined.query
        if date_cond is not None:
            base_query = base_query.filter(date_cond)
        
        # Total users
        total_users = base_query.count() or 0
        
        # Unique organizations
        try:
            org_query = db.session.query(func.count(func.distinct(UserPIICombined.organization_name)))
            if date_cond is not None:
                org_query = org_query.filter(date_cond)
            unique_orgs = org_query.scalar() or 0
        except:
            unique_orgs = 0
        
        # Top domain
        top_domain = None
        try:
            domain_query = db.session.query(
                UserPIICombined.domain,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.domain.isnot(None),
                UserPIICombined.domain != ''
            )
            if date_cond is not None:
                domain_query = domain_query.filter(date_cond)
            top_domain_result = domain_query.group_by(
                UserPIICombined.domain
            ).order_by(desc('count')).first()
            
            top_domain = top_domain_result[0] if top_domain_result else None
        except:
            top_domain = None
        
        # Top city
        top_city = None
        try:
            city_query = db.session.query(
                UserPIICombined.city,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.city.isnot(None),
                UserPIICombined.city != ''
            )
            if date_cond is not None:
                city_query = city_query.filter(date_cond)
            top_city_result = city_query.group_by(
                UserPIICombined.city
            ).order_by(desc('count')).first()
            
            top_city = top_city_result[0] if top_city_result else None
        except:
            top_city = None
        
        # Additional stats
        # Total countries
        try:
            unique_countries = db.session.query(func.count(func.distinct(UserPIICombined.country))).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != ''
            ).scalar() or 0
        except:
            unique_countries = 0
        
        # Users with GitHub
        try:
            github_query = UserPIICombined.query.filter(
                UserPIICombined.github_url.isnot(None),
                UserPIICombined.github_url != ''
            )
            if date_cond is not None:
                github_query = github_query.filter(date_cond)
            users_with_github = github_query.count() or 0
        except:
            users_with_github = 0
        
        # Users with LinkedIn
        try:
            linkedin_query = UserPIICombined.query.filter(
                UserPIICombined.linkedin_url.isnot(None),
                UserPIICombined.linkedin_url != ''
            )
            if date_cond is not None:
                linkedin_query = linkedin_query.filter(date_cond)
            users_with_linkedin = linkedin_query.count() or 0
        except:
            users_with_linkedin = 0
        
        # Book of Business registrations (bob_match = True)
        try:
            bob_query = UserPIICombined.query.filter(UserPIICombined.bob_match == True)
            if date_cond is not None:
                bob_query = bob_query.filter(date_cond)
            book_of_business_registrations = bob_query.count() or 0
        except Exception:
            book_of_business_registrations = 0

        # Skill Lab / Skillboost profiles: total, verified, verification rate (all rows in skillboost_profile)
        total_skillboost_profiles = 0
        verified_skillboost_profiles = 0
        skillboost_verification_rate = None
        # Skill Lab credits: allocated, not sent, sent (verified + credit_link_id set)
        skillboost_credits_allocated = 0
        skillboost_credits_not_sent = 0
        skillboost_credits_sent = 0
        try:
            total_skillboost_profiles = SkillboostProfile.query.count() or 0
            verified_skillboost_profiles = SkillboostProfile.query.filter(SkillboostProfile.valid == True).count() or 0
            if total_skillboost_profiles > 0:
                skillboost_verification_rate = round(100.0 * verified_skillboost_profiles / total_skillboost_profiles, 1)
            skillboost_credits_allocated = SkillboostProfile.query.filter(
                SkillboostProfile.valid == True,
                SkillboostProfile.credit_link_id.isnot(None)
            ).count() or 0
            skillboost_credits_not_sent = SkillboostProfile.query.filter(
                SkillboostProfile.valid == True,
                SkillboostProfile.credit_link_id.isnot(None),
                SkillboostProfile.email_sent_at.is_(None)
            ).count() or 0
            skillboost_credits_sent = SkillboostProfile.query.filter(
                SkillboostProfile.valid == True,
                SkillboostProfile.credit_link_id.isnot(None),
                SkillboostProfile.email_sent_at.isnot(None)
            ).count() or 0
        except Exception:
            pass

        # Skill Lab Submission Verification stats
        total_skilllab_submissions = 0
        verified_skilllab_submissions = 0
        skilllab_submission_verification_rate = None
        try:
            total_skilllab_submissions = SkillLabSubmission.query.count() or 0
            verified_skilllab_submissions = SkillLabSubmission.query.filter(SkillLabSubmission.valid == True).count() or 0
            if total_skilllab_submissions > 0:
                skilllab_submission_verification_rate = round(100.0 * verified_skilllab_submissions / total_skilllab_submissions, 1)
        except Exception:
            pass

        # Code Lab Submission Verification stats
        total_codelab_submissions = 0
        verified_codelab_submissions = 0
        codelab_submission_verification_rate = None
        try:
            total_codelab_submissions = CodeLabSubmission.query.count() or 0
            verified_codelab_submissions = CodeLabSubmission.query.filter(CodeLabSubmission.valid == True).count() or 0
            if total_codelab_submissions > 0:
                codelab_submission_verification_rate = round(100.0 * verified_codelab_submissions / total_codelab_submissions, 1)
        except Exception:
            pass
        
        # Top organization
        top_org = None
        try:
            org_query = db.session.query(
                UserPIICombined.organization_name,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.organization_name.isnot(None),
                UserPIICombined.organization_name != ''
            )
            if date_cond is not None:
                org_query = org_query.filter(date_cond)
            top_org_result = org_query.group_by(
                UserPIICombined.organization_name
            ).order_by(desc('count')).first()
            
            top_org = top_org_result[0] if top_org_result else None
        except:
            top_org = None
        
        # Average age (from date_of_birth) - Optimized using SQL
        avg_age = None
        try:
            today = datetime.now().date()
            
            # Use SQL to calculate age instead of loading all records
            # PostgreSQL AGE function returns interval, extract year
            age_query = db.session.query(
                func.avg(
                    func.extract('year', func.age(today, UserPIICombined.date_of_birth))
                )
            ).filter(
                UserPIICombined.date_of_birth.isnot(None)
            )
            if date_cond is not None:
                age_query = age_query.filter(date_cond)
            
            avg_age_result = age_query.scalar()
            if avg_age_result:
                avg_age = int(avg_age_result)
        except Exception as e:
            # Fallback to Python calculation if SQL fails
            try:
                today = datetime.now().date()
                dob_query = UserPIICombined.query.filter(
                    UserPIICombined.date_of_birth.isnot(None)
                )
                if date_cond is not None:
                    dob_query = dob_query.filter(date_cond)
                # Limit to 10000 records for fallback
                users_with_dob = dob_query.limit(10000).all()
                
                if users_with_dob:
                    ages = []
                    for user in users_with_dob:
                        if user.date_of_birth:
                            age = today.year - user.date_of_birth.year - (
                                (today.month, today.day) < (user.date_of_birth.month, user.date_of_birth.day)
                            )
                            ages.append(age)
                    
                    if ages:
                        avg_age = int(sum(ages) / len(ages))
            except:
                avg_age = None
        
        # APAC countries list (excluding India)
        APAC_COUNTRIES = [
            'Australia', 'Bangladesh', 'Bhutan', 'Brunei', 'Cambodia', 'China',
            'Fiji', 'Hong Kong', 'Indonesia', 'Japan', 'Laos', 'Malaysia',
            'Maldives', 'Mongolia', 'Myanmar', 'Nepal', 'New Zealand',
            'North Korea', 'Pakistan', 'Papua New Guinea', 'Philippines',
            'Singapore', 'South Korea', 'Sri Lanka', 'Taiwan', 'Thailand',
            'Timor-Leste', 'Vietnam', 'APAC', 'Asia Pacific'
        ]
        # SEA (Southeast Asia)
        SEA_COUNTRIES = [
            'Brunei', 'Cambodia', 'Indonesia', 'Laos', 'Malaysia', 'Myanmar',
            'Philippines', 'Singapore', 'Thailand', 'Timor-Leste', 'Vietnam'
        ]
        # ANZ (Australia & New Zealand)
        ANZ_COUNTRIES = ['Australia', 'New Zealand']
        # East Asia
        EAST_ASIA_COUNTRIES = [
            'China', 'Hong Kong', 'Japan', 'South Korea', 'North Korea',
            'Taiwan', 'Mongolia'
        ]
        
        # Users from APAC except India
        apac_except_india_count = 0
        try:
            # Filter for APAC countries (case-insensitive), excluding India
            apac_conditions = [UserPIICombined.country.ilike(f'%{country}%') for country in APAC_COUNTRIES]
            if apac_conditions:
                apac_query = base_query.filter(
                    UserPIICombined.country.isnot(None),
                    UserPIICombined.country != '',
                    ~UserPIICombined.country.ilike('%India%'),
                    or_(*apac_conditions)
                )
            else:
                # If no APAC countries defined, just exclude India
                apac_query = base_query.filter(
                    UserPIICombined.country.isnot(None),
                    UserPIICombined.country != '',
                    ~UserPIICombined.country.ilike('%India%')
                )
            apac_except_india_count = apac_query.count() or 0
        except Exception as e:
            print(f"Error calculating APAC users: {e}")
            import traceback
            traceback.print_exc()
            apac_except_india_count = 0
        
        # Top state and city from India (with counts)
        top_india_state = None
        top_india_city = None
        top_india_state_count = None
        top_india_city_count = None
        try:
            india_state_query = db.session.query(
                UserPIICombined.state,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.ilike('%India%'),
                UserPIICombined.state.isnot(None),
                UserPIICombined.state != ''
            )
            if date_cond is not None:
                india_state_query = india_state_query.filter(date_cond)
            top_india_state_result = india_state_query.group_by(
                UserPIICombined.state
            ).order_by(desc('count')).first()
            if top_india_state_result:
                top_india_state = top_india_state_result[0]
                top_india_state = normalize_state(top_india_state) if top_india_state else None
                top_india_state_count = top_india_state_result[1]
            
            india_city_query = db.session.query(
                UserPIICombined.city,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.ilike('%India%'),
                UserPIICombined.city.isnot(None),
                UserPIICombined.city != ''
            )
            if date_cond is not None:
                india_city_query = india_city_query.filter(date_cond)
            top_india_city_result = india_city_query.group_by(
                UserPIICombined.city
            ).order_by(desc('count')).first()
            if top_india_city_result:
                top_india_city = top_india_city_result[0]
                top_india_city_count = top_india_city_result[1]
        except Exception as e:
            print(f"Error calculating India stats: {e}")
            top_india_state = None
            top_india_city = None
            top_india_state_count = None
            top_india_city_count = None
        
        # Top country from APAC except India (with count)
        top_apac_country = None
        top_apac_country_count = None
        try:
            # Filter for APAC countries (case-insensitive), excluding India
            apac_conditions = [UserPIICombined.country.ilike(f'%{country}%') for country in APAC_COUNTRIES]
            apac_country_query = db.session.query(
                UserPIICombined.country,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                ~UserPIICombined.country.ilike('%India%')
            )
            if apac_conditions:
                apac_country_query = apac_country_query.filter(or_(*apac_conditions))
            if date_cond is not None:
                apac_country_query = apac_country_query.filter(date_cond)
            top_apac_country_result = apac_country_query.group_by(
                UserPIICombined.country
            ).order_by(desc('count')).first()
            if top_apac_country_result:
                top_apac_country = top_apac_country_result[0]
                top_apac_country_count = top_apac_country_result[1]
        except Exception as e:
            print(f"Error calculating top APAC country: {e}")
            import traceback
            traceback.print_exc()
            top_apac_country = None
            top_apac_country_count = None

        # SEA, ANZ, East Asia: per-region count and top country (base_query has date filter)
        sea_registrations = 0
        sea_top_country = None
        anz_registrations = 0
        anz_top_country = None
        east_asia_registrations = 0
        east_asia_top_country = None
        try:
            for region_name, countries in [
                ('sea', SEA_COUNTRIES),
                ('anz', ANZ_COUNTRIES),
                ('east_asia', EAST_ASIA_COUNTRIES)
            ]:
                conds = [UserPIICombined.country.ilike(f'%{c}%') for c in countries]
                region_query = base_query.filter(
                    UserPIICombined.country.isnot(None),
                    UserPIICombined.country != '',
                    or_(*conds)
                )
                count = region_query.count() or 0
                top_q = db.session.query(
                    UserPIICombined.country,
                    func.count(UserPIICombined.id).label('count')
                ).filter(
                    UserPIICombined.country.isnot(None),
                    UserPIICombined.country != '',
                    or_(*conds)
                )
                if date_cond is not None:
                    top_q = top_q.filter(date_cond)
                top_result = top_q.group_by(UserPIICombined.country).order_by(desc('count')).first()
                top_country = top_result[0] if top_result else None
                if region_name == 'sea':
                    sea_registrations = count
                    sea_top_country = top_country
                elif region_name == 'anz':
                    anz_registrations = count
                    anz_top_country = top_country
                else:
                    east_asia_registrations = count
                    east_asia_top_country = top_country
        except Exception as e:
            print(f"Error calculating region stats (SEA/ANZ/East Asia): {e}")

        # India: count and top state (same period filter)
        india_registrations = 0
        try:
            india_query = base_query.filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                UserPIICombined.country.ilike('%India%')
            )
            india_registrations = india_query.count() or 0
        except Exception as e:
            print(f"Error calculating India stats: {e}")

        # Previous period metrics for week-on-week / period-on-period
        prev_total_users = None
        prev_apac_users = None
        prev_avg_age = None
        prev_start, current_start = _get_previous_period_range(period)
        prev_cond = _previous_period_filter(prev_start, current_start) if prev_start and current_start else None
        if prev_cond is not None:
            try:
                prev_total_users = UserPIICombined.query.filter(prev_cond).count() or 0
            except Exception:
                prev_total_users = 0
            try:
                apac_conditions = [UserPIICombined.country.ilike(f'%{c}%') for c in APAC_COUNTRIES]
                prev_apac_q = UserPIICombined.query.filter(
                    prev_cond,
                    UserPIICombined.country.isnot(None),
                    UserPIICombined.country != '',
                    ~UserPIICombined.country.ilike('%India%')
                )
                if apac_conditions:
                    prev_apac_q = prev_apac_q.filter(or_(*apac_conditions))
                prev_apac_users = prev_apac_q.count() or 0
            except Exception:
                prev_apac_users = 0
            try:
                today = datetime.now().date()
                prev_age_q = db.session.query(
                    func.avg(func.extract('year', func.age(today, UserPIICombined.date_of_birth)))
                ).filter(UserPIICombined.date_of_birth.isnot(None)).filter(prev_cond)
                prev_avg_result = prev_age_q.scalar()
                prev_avg_age = int(prev_avg_result) if prev_avg_result else None
            except Exception:
                prev_avg_age = None

        # Optional MCQ completion by track (total submissions, passed 6+ per track)
        optional_mcq_by_track = []
        try:
            for track_num in (1, 2, 3):
                rows = OptionalMcqResponse.query.filter(OptionalMcqResponse.track_number == track_num).all()
                total = len(rows)
                passed_6 = 0
                for r in rows:
                    auto = get_response_score(r)
                    if auto.get('correct_count', 0) >= 6:
                        passed_6 += 1
                optional_mcq_by_track.append({'track': track_num, 'total': total, 'passed_6': passed_6})
        except Exception:
            optional_mcq_by_track = [{'track': t, 'total': 0, 'passed_6': 0} for t in (1, 2, 3)]

        # Top 5 winners: 10/10 on all 3 tracks, ordered by completion time (max created_at) ascending
        optional_mcq_top5_winners = []
        try:
            from collections import defaultdict
            by_email = defaultdict(list)
            for r in OptionalMcqResponse.query.all():
                by_email[r.email].append(r)
            winners = []
            for email, rows in by_email.items():
                if len(rows) != 3:
                    continue
                by_track = {r.track_number: r for r in rows}
                if set(by_track.keys()) != {1, 2, 3}:
                    continue
                all_10 = True
                completion_at = None
                for t in (1, 2, 3):
                    r = by_track[t]
                    auto = get_response_score(r)
                    if auto.get('correct_count', 0) != 10:
                        all_10 = False
                        break
                    if r.created_at:
                        completion_at = r.created_at if completion_at is None else max(completion_at, r.created_at)
                if all_10 and completion_at is not None:
                    leader_name = getattr(by_track.get(1), 'leader_name', None) or getattr(rows[0], 'leader_name', None) if rows else None
                    winners.append({'email': email, 'completed_at': completion_at, 'leader_name': leader_name})
            winners.sort(key=lambda x: x['completed_at'])
            for w in winners[:5]:
                pii = UserPIICombined.query.filter_by(email=w['email']).first()
                name = (pii.name if pii and pii.name else w.get('leader_name')) or w['email']
                optional_mcq_top5_winners.append({
                    'name': name,
                    'email': w['email'],
                    'completed_at': w['completed_at'].isoformat() if hasattr(w['completed_at'], 'isoformat') else str(w['completed_at']),
                })
        except Exception:
            optional_mcq_top5_winners = []
        
        return {
            'total_users': total_users,
            'unique_organizations': unique_orgs,
            'unique_countries': unique_countries,
            'top_domain': top_domain or 'N/A',
            'top_city': top_city or 'N/A',
            'top_organization': top_org or 'N/A',
            'users_with_github': users_with_github,
            'users_with_linkedin': users_with_linkedin,
            'average_age': avg_age,
            'apac_except_india_users': apac_except_india_count,
            'top_india_state': top_india_state or 'N/A',
            'top_india_city': top_india_city or 'N/A',
            'top_india_state_count': top_india_state_count,
            'top_india_city_count': top_india_city_count,
            'top_india_location_count': top_india_city_count if top_india_city_count is not None else top_india_state_count,
            'top_apac_country': top_apac_country or 'N/A',
            'top_apac_country_count': top_apac_country_count,
            'sea_registrations': sea_registrations,
            'sea_top_country': sea_top_country or 'N/A',
            'anz_registrations': anz_registrations,
            'anz_top_country': anz_top_country or 'N/A',
            'east_asia_registrations': east_asia_registrations,
            'east_asia_top_country': east_asia_top_country or 'N/A',
            'india_registrations': india_registrations,
            'book_of_business_registrations': book_of_business_registrations,
            'total_skillboost_profiles': total_skillboost_profiles,
            'verified_skillboost_profiles': verified_skillboost_profiles,
            'skillboost_verification_rate': skillboost_verification_rate,
            'skillboost_credits_allocated': skillboost_credits_allocated,
            'skillboost_credits_not_sent': skillboost_credits_not_sent,
            'skillboost_credits_sent': skillboost_credits_sent,
            'total_skilllab_submissions': total_skilllab_submissions,
            'verified_skilllab_submissions': verified_skilllab_submissions,
            'skilllab_submission_verification_rate': skilllab_submission_verification_rate,
            'total_codelab_submissions': total_codelab_submissions,
            'verified_codelab_submissions': verified_codelab_submissions,
            'codelab_submission_verification_rate': codelab_submission_verification_rate,
            'optional_mcq_by_track': optional_mcq_by_track,
            'previous_period_total_users': prev_total_users,
            'previous_period_apac_users': prev_apac_users,
            'previous_period_average_age': prev_avg_age
        }
    except Exception as e:
        # Return empty data instead of error
        return {
            'total_users': 0,
            'unique_organizations': 0,
            'top_domain': 'N/A',
            'top_city': 'N/A',
            'average_age': None,
            'apac_except_india_users': 0,
            'top_india_state': 'N/A',
            'top_india_city': 'N/A',
            'top_india_state_count': None,
            'top_india_city_count': None,
            'top_india_location_count': None,
            'top_apac_country': 'N/A',
            'top_apac_country_count': None,
            'sea_registrations': 0,
            'sea_top_country': 'N/A',
            'anz_registrations': 0,
            'anz_top_country': 'N/A',
            'east_asia_registrations': 0,
            'east_asia_top_country': 'N/A',
            'india_registrations': 0,
            'book_of_business_registrations': 0,
            'total_skillboost_profiles': 0,
            'verified_skillboost_profiles': 0,
            'skillboost_verification_rate': None,
            'skillboost_credits_allocated': 0,
            'skillboost_credits_not_sent': 0,
            'skillboost_credits_sent': 0,
            'total_skilllab_submissions': 0,
            'verified_skilllab_submissions': 0,
            'skilllab_submission_verification_rate': None,
            'total_codelab_submissions': 0,
            'verified_codelab_submissions': 0,
            'codelab_submission_verification_rate': None,
            'optional_mcq_by_track': [{'track': t, 'total': 0, 'passed_6': 0} for t in (1, 2, 3)],
            'optional_mcq_top5_winners': [],
            'previous_period_total_users': None,
            'previous_period_apac_users': None,
            'previous_period_average_age': None
        }


@bp.route('/widget-stats', methods=['GET'])
@require_page_access('dashboard')
def get_widget_stats():
    """Get lightweight stats for iOS widget"""
    try:
        # Get today's signups
        today = datetime.now().date()
        today_signups = UserPIICombined.query.filter(
            func.date(UserPIICombined.registered_at) == today
        ).count() or 0
        
        # Get total users
        total_users = UserPIICombined.query.count() or 0
        
        # Get active users (registered in last 30 days)
        active_cutoff = datetime.now() - timedelta(days=30)
        active_users = UserPIICombined.query.filter(
            UserPIICombined.registered_at >= active_cutoff
        ).count() or 0
        
        return jsonify({
            'total_users': total_users,
            'today_signups': today_signups,
            'active_users': active_users,
            'last_updated': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'total_users': 0,
            'today_signups': 0,
            'active_users': 0,
            'last_updated': datetime.utcnow().isoformat()
        }), 200


@bp.route('/charts', methods=['GET'])
@require_page_access('dashboard')
def get_charts():
    """Get chart data for dashboard (cached)"""
    from server.utils.cache import cache_result
    
    @cache_result(ttl=300)  # Cache for 5 minutes
    def _get_charts(period):
        """Internal function to fetch charts (cached)"""
        return _fetch_charts_data(period)
    
    try:
        period = request.args.get('period', 'all')
        result = _get_charts(period)
        return jsonify(result), 200
    except Exception as e:
        # Return empty data instead of error
        return jsonify({
            'gender_distribution': [],
            'registration_source_bifurcation': [{'label': 'Google', 'value': 0}, {'label': 'Outreach', 'value': 0}, {'label': 'Marketing', 'value': 0}, {'label': 'Ads', 'value': 0}, {'label': 'Hack2skill', 'value': 0}, {'label': 'Other', 'value': 0}],
            'top_domains': [],
            'top_cities': [],
            'top_cities_outside_india': [],
            'top_states': [],
            'country_distribution': [],
            'top_organizations': [],
            'class_stream_distribution': [],
            'designation_distribution': [],
            'occupation_distribution': [],
            'age_groups': [],
            'registration_trends': [],
            'social_media': [],
            'india_state_registrations': [],
            'apac_country_registrations': []
        }), 200


def _utm_to_registration_source(utm_medium):
    """Map utm_medium (or combined UTM string) to registration source label for bifurcation chart.
    Rules: google/email -> Google; outreach/community/college/partnership -> Outreach;
    h2s/sendy/h2s social/webengage -> Marketing; ad -> Ads; homepage -> Hack2skill; else -> Other.
    """
    if not utm_medium or not str(utm_medium).strip():
        return 'Other'
    u = str(utm_medium).strip().lower()
    if 'google' in u or 'email' in u:
        return 'Google'
    if any(x in u for x in ('outreach', 'community', 'college', 'partnership')):
        return 'Outreach'
    if 'h2s social' in u or 'h2s' in u or 'sendy' in u or 'webengage' in u:
        return 'Marketing'
    if 'ad' in u:
        return 'Ads'
    if 'homepage' in u:
        return 'Hack2skill'
    return 'Other'


def _fetch_charts_data(period, summary=None):
    """Internal function to fetch charts data. If summary is provided (e.g. from combined /data), reuse total_users for registration source to avoid extra count query."""
    try:
        cutoff_date = _get_period_dates(period)
        date_cond = _date_filter_condition(cutoff_date)
        
        base_query = UserPIICombined.query
        if date_cond is not None:
            base_query = base_query.filter(date_cond)
        
        # Gender distribution
        gender_distribution = []
        try:
            gender_query = db.session.query(
                UserPIICombined.gender,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.gender.isnot(None),
                UserPIICombined.gender != ''
            )
            if date_cond is not None:
                gender_query = gender_query.filter(date_cond)
            gender_data = gender_query.group_by(
                UserPIICombined.gender
            ).all()
            gender_distribution = [{'label': g[0], 'value': g[1]} for g in gender_data]
        except:
            gender_distribution = []
        
        # Registration source bifurcation: map UTM (contains) -> Google, Outreach, Marketing, Ads, Hack2skill, Other
        registration_source_bifurcation = []
        try:
            utm_query = db.session.query(
                UserPIICombined.utm_medium,
                func.count(UserPIICombined.id).label('count')
            )
            if date_cond is not None:
                utm_query = utm_query.filter(date_cond)
            utm_query = utm_query.group_by(UserPIICombined.utm_medium).all()
            agg = {'Google': 0, 'Outreach': 0, 'Marketing': 0, 'Ads': 0, 'Hack2skill': 0, 'Other': 0}
            for utm_val, cnt in utm_query:
                label = _utm_to_registration_source(utm_val)
                agg[label] = agg.get(label, 0) + (cnt or 0)
            registration_source_bifurcation = [
                {'label': 'Google', 'value': agg['Google']},
                {'label': 'Outreach', 'value': agg['Outreach']},
                {'label': 'Marketing', 'value': agg['Marketing']},
                {'label': 'Ads', 'value': agg['Ads']},
                {'label': 'Hack2skill', 'value': agg['Hack2skill']},
                {'label': 'Other', 'value': agg['Other']}
            ]
        except Exception:
            registration_source_bifurcation = [
                {'label': 'Google', 'value': 0}, {'label': 'Outreach', 'value': 0},
                {'label': 'Marketing', 'value': 0}, {'label': 'Ads', 'value': 0},
                {'label': 'Hack2skill', 'value': 0}, {'label': 'Other', 'value': 0}
            ]
        
        # Top domains (top 10)
        top_domains_data = []
        try:
            domains_query = db.session.query(
                UserPIICombined.domain,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.domain.isnot(None),
                UserPIICombined.domain != ''
            )
            if date_cond is not None:
                domains_query = domains_query.filter(date_cond)
            top_domains = domains_query.group_by(
                UserPIICombined.domain
            ).order_by(desc('count')).limit(10).all()
            top_domains_data = [{'label': d[0], 'value': d[1]} for d in top_domains]
        except:
            top_domains_data = []
        
        # Top cities (top 10)
        top_cities_data = []
        try:
            cities_query = db.session.query(
                UserPIICombined.city,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.city.isnot(None),
                UserPIICombined.city != ''
            )
            if date_cond is not None:
                cities_query = cities_query.filter(date_cond)
            top_cities = cities_query.group_by(
                UserPIICombined.city
            ).order_by(desc('count')).limit(10).all()
            top_cities_data = [{'label': c[0], 'value': c[1]} for c in top_cities]
        except:
            top_cities_data = []
        
        # Top cities outside India (top 10), label: "City (Country)"
        top_cities_outside_india_data = []
        try:
            cities_outside_query = db.session.query(
                UserPIICombined.city,
                UserPIICombined.country,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.city.isnot(None),
                UserPIICombined.city != '',
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                ~UserPIICombined.country.ilike('%India%')
            )
            if date_cond is not None:
                cities_outside_query = cities_outside_query.filter(date_cond)
            cities_outside = cities_outside_query.group_by(
                UserPIICombined.city,
                UserPIICombined.country
            ).order_by(desc('count')).limit(10).all()
            top_cities_outside_india_data = [
                {'label': f'{c[0]} ({c[1]})', 'value': c[2]}
                for c in cities_outside
            ]
        except Exception:
            top_cities_outside_india_data = []
        
        # Top states (top 10)
        top_states_data = []
        try:
            states_query = db.session.query(
                UserPIICombined.state,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.state.isnot(None),
                UserPIICombined.state != ''
            )
            if date_cond is not None:
                states_query = states_query.filter(date_cond)
            top_states = states_query.group_by(
                UserPIICombined.state
            ).order_by(desc('count')).limit(10).all()
            top_states_data = [{'label': s[0], 'value': s[1]} for s in top_states]
        except:
            top_states_data = []
        
        # Country distribution
        country_distribution = []
        try:
            countries_query = db.session.query(
                UserPIICombined.country,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != ''
            )
            if date_cond is not None:
                countries_query = countries_query.filter(date_cond)
            countries = countries_query.group_by(
                UserPIICombined.country
            ).order_by(desc('count')).limit(10).all()
            country_distribution = [{'label': c[0], 'value': c[1]} for c in countries]
        except:
            country_distribution = []
        
        # Top organizations (top 10) – only PROFESSIONAL, STARTUP, FREELANCE (exclude students); exclude NA/N/A
        top_organizations_data = []
        try:
            occupation_filter = or_(
                UserPIICombined.occupation.ilike('%professional%'),
                UserPIICombined.occupation.ilike('%startup%'),
                UserPIICombined.occupation.ilike('%freelance%')
            )
            exclude_na = ~or_(
                func.lower(func.trim(UserPIICombined.organization_name)) == 'na',
                func.lower(func.trim(UserPIICombined.organization_name)) == 'n/a'
            )
            orgs_query = db.session.query(
                UserPIICombined.organization_name,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.organization_name.isnot(None),
                UserPIICombined.organization_name != '',
                occupation_filter,
                exclude_na
            )
            if date_cond is not None:
                orgs_query = orgs_query.filter(date_cond)
            top_orgs = orgs_query.group_by(
                UserPIICombined.organization_name
            ).order_by(desc('count')).limit(10).all()
            top_organizations_data = [{'label': o[0], 'value': o[1]} for o in top_orgs]
        except Exception:
            top_organizations_data = []
        
        # Class stream distribution
        class_stream_data = []
        try:
            streams_query = db.session.query(
                UserPIICombined.class_stream,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.class_stream.isnot(None),
                UserPIICombined.class_stream != ''
            )
            if date_cond is not None:
                streams_query = streams_query.filter(date_cond)
            streams = streams_query.group_by(
                UserPIICombined.class_stream
            ).order_by(desc('count')).all()
            class_stream_data = [{'label': s[0], 'value': s[1]} for s in streams]
        except:
            class_stream_data = []
        
        # Designation distribution (top 10)
        designation_data = []
        try:
            designation_query = db.session.query(
                UserPIICombined.designation,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.designation.isnot(None),
                UserPIICombined.designation != ''
            )
            if date_cond is not None:
                designation_query = designation_query.filter(date_cond)
            designations = designation_query.group_by(
                UserPIICombined.designation
            ).order_by(desc('count')).limit(10).all()
            designation_data = [{'label': d[0], 'value': d[1]} for d in designations]
        except:
            designation_data = []
        
        # Top occupations (top 10)
        occupation_data = []
        try:
            occupation_query = db.session.query(
                UserPIICombined.occupation,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.occupation.isnot(None),
                UserPIICombined.occupation != ''
            )
            if date_cond is not None:
                occupation_query = occupation_query.filter(date_cond)
            occupations = occupation_query.group_by(
                UserPIICombined.occupation
            ).order_by(desc('count')).limit(10).all()
            occupation_data = [{'label': o[0], 'value': o[1]} for o in occupations]
        except:
            occupation_data = []
        
        # Age groups distribution - Optimized using SQL CASE statements
        age_groups_data = []
        try:
            today = datetime.now().date()
            
            # Use SQL CASE to calculate age groups directly in database
            age_expr = func.extract('year', func.age(today, UserPIICombined.date_of_birth))
            age_group_expr = case(
                (age_expr.between(18, 25), '18-25'),
                (age_expr.between(26, 35), '26-35'),
                (age_expr.between(36, 45), '36-45'),
                (age_expr.between(46, 55), '46-55'),
                (age_expr > 55, '56+'),
                else_=None
            )
            
            age_query = db.session.query(
                age_group_expr.label('age_group'),
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.date_of_birth.isnot(None),
                age_expr >= 18  # Only count adults
            )
            if date_cond is not None:
                age_query = age_query.filter(date_cond)
            
            age_results = age_query.group_by(age_group_expr).all()
            age_groups_data = [{'label': r[0], 'value': r[1]} for r in age_results if r[0] is not None]
        except Exception as e:
            # Fallback to Python calculation if SQL fails
            try:
                print(f"SQL age calculation failed, using fallback: {e}")
                today = datetime.now().date()
                dob_query = UserPIICombined.query.filter(
                    UserPIICombined.date_of_birth.isnot(None)
                )
                if date_cond is not None:
                    dob_query = dob_query.filter(date_cond)
                # Limit to 10000 records for fallback
                users_with_dob = dob_query.limit(10000).all()
                
                age_ranges = {
                    '18-25': 0,
                    '26-35': 0,
                    '36-45': 0,
                    '46-55': 0,
                    '56+': 0
                }
                
                for user in users_with_dob:
                    if user.date_of_birth:
                        age = today.year - user.date_of_birth.year - (
                            (today.month, today.day) < (user.date_of_birth.month, user.date_of_birth.day)
                        )
                        
                        if 18 <= age <= 25:
                            age_ranges['18-25'] += 1
                        elif 26 <= age <= 35:
                            age_ranges['26-35'] += 1
                        elif 36 <= age <= 45:
                            age_ranges['36-45'] += 1
                        elif 46 <= age <= 55:
                            age_ranges['46-55'] += 1
                        elif age > 55:
                            age_ranges['56+'] += 1
                
                age_groups_data = [{'label': k, 'value': v} for k, v in age_ranges.items() if v > 0]
            except Exception as e2:
                print(f"Error calculating age groups: {e2}")
                age_groups_data = []
        
        # Registration trends (daily) using registered_at column
        registration_trends = []
        try:
            # Start date from period: Jan 15 for 'all', or period cutoff
            if cutoff_date:
                start_date = cutoff_date
            else:
                # For 'all' data: line charts start from Jan 15 (current or previous year)
                now = datetime.now()
                start_date = datetime(now.year, 1, 15)
                if start_date.date() > now.date():
                    start_date = datetime(now.year - 1, 1, 15)
            # Use date_trunc for PostgreSQL compatibility, filter out NULL registered_at
            trends = db.session.query(
                func.date_trunc('day', UserPIICombined.registered_at).label('date'),
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.registered_at.isnot(None),
                UserPIICombined.registered_at >= start_date
            ).group_by(
                func.date_trunc('day', UserPIICombined.registered_at)
            ).order_by('date').all()
            
            # Create a complete date range to fill in missing days with 0
            date_dict = {}
            for t in trends:
                # Convert to date object
                if isinstance(t[0], datetime):
                    date_key = t[0].date()
                else:
                    date_key = t[0]
                date_dict[date_key] = t[1]
            
            complete_trends = []
            current_date = start_date.date()
            today = datetime.now().date()
            
            while current_date <= today:
                count = date_dict.get(current_date, 0)
                complete_trends.append({
                    'label': current_date.strftime('%b %d'),
                    'value': count,
                    'date': current_date.isoformat()
                })
                current_date += timedelta(days=1)
            
            registration_trends = complete_trends
        except Exception as e:
            print(f"Error calculating registration trends: {e}")
            registration_trends = []
        
        # Social media presence
        social_media_data = []
        try:
            github_query = UserPIICombined.query.filter(
                UserPIICombined.github_url.isnot(None),
                UserPIICombined.github_url != ''
            )
            if date_cond is not None:
                github_query = github_query.filter(date_cond)
            github_count = github_query.count() or 0
            
            linkedin_query = UserPIICombined.query.filter(
                UserPIICombined.linkedin_url.isnot(None),
                UserPIICombined.linkedin_url != ''
            )
            if date_cond is not None:
                linkedin_query = linkedin_query.filter(date_cond)
            linkedin_count = linkedin_query.count() or 0
            
            both_query = UserPIICombined.query.filter(
                UserPIICombined.github_url.isnot(None),
                UserPIICombined.github_url != '',
                UserPIICombined.linkedin_url.isnot(None),
                UserPIICombined.linkedin_url != ''
            )
            if date_cond is not None:
                both_query = both_query.filter(date_cond)
            both_count = both_query.count() or 0
            
            # Get total for period
            period_total = base_query.count()
            
            github_only = max(0, github_count - both_count)
            linkedin_only = max(0, linkedin_count - both_count)
            neither = max(0, period_total - github_count - linkedin_count + both_count)
            
            social_media_data = [
                {'label': 'GitHub Only', 'value': github_only},
                {'label': 'LinkedIn Only', 'value': linkedin_only},
                {'label': 'Both', 'value': both_count},
                {'label': 'Neither', 'value': neither}
            ]
            
            # Filter out zero values
            social_media_data = [item for item in social_media_data if item['value'] > 0]
        except:
            social_media_data = []

        # India state-wise registration counts (for heatmap)
        india_state_registrations = []
        try:
            india_state_query = db.session.query(
                UserPIICombined.state,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.ilike('%India%'),
                UserPIICombined.state.isnot(None),
                UserPIICombined.state != ''
            )
            if date_cond is not None:
                india_state_query = india_state_query.filter(date_cond)
            india_states = india_state_query.group_by(UserPIICombined.state).order_by(desc('count')).all()
            india_state_registrations = [{'state': s[0], 'value': s[1]} for s in india_states]
        except Exception:
            india_state_registrations = []

        # APAC country-wise registration counts (for heatmap) – outside India only (“Outside Indian Registrations”)
        apac_country_registrations = []
        try:
            APAC_FOR_MAP_EXCL_INDIA = [
                'Australia', 'Bangladesh', 'Bhutan', 'Brunei', 'Cambodia', 'China',
                'Fiji', 'Hong Kong', 'Indonesia', 'Japan', 'Laos', 'Malaysia', 'Maldives',
                'Mongolia', 'Myanmar', 'Nepal', 'New Zealand', 'North Korea', 'Pakistan',
                'Papua New Guinea', 'Philippines', 'Singapore', 'South Korea', 'Sri Lanka',
                'Taiwan', 'Thailand', 'Timor-Leste', 'Vietnam', 'APAC', 'Asia Pacific'
            ]
            apac_conditions = [UserPIICombined.country.ilike(f'%{c}%') for c in APAC_FOR_MAP_EXCL_INDIA]
            apac_country_query = db.session.query(
                UserPIICombined.country,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                ~UserPIICombined.country.ilike('%India%')
            )
            if apac_conditions:
                apac_country_query = apac_country_query.filter(or_(*apac_conditions))
            if date_cond is not None:
                apac_country_query = apac_country_query.filter(date_cond)
            apac_countries = apac_country_query.group_by(UserPIICombined.country).order_by(desc('count')).all()
            apac_country_registrations = [{'country': c[0], 'value': c[1]} for c in apac_countries]
        except Exception:
            apac_country_registrations = []

        return {
            'gender_distribution': gender_distribution,
            'registration_source_bifurcation': registration_source_bifurcation,
            'top_domains': top_domains_data,
            'top_cities': top_cities_data,
            'top_cities_outside_india': top_cities_outside_india_data,
            'top_states': top_states_data,
            'country_distribution': country_distribution,
            'top_organizations': top_organizations_data,
            'class_stream_distribution': class_stream_data,
            'designation_distribution': designation_data,
            'occupation_distribution': occupation_data,
            'age_groups': age_groups_data,
            'registration_trends': registration_trends,
            'social_media': social_media_data,
            'india_state_registrations': india_state_registrations,
            'apac_country_registrations': apac_country_registrations
        }
    except Exception as e:
        # Return empty data instead of error
        return {
            'gender_distribution': [],
            'registration_source_bifurcation': [{'label': 'Google', 'value': 0}, {'label': 'Outreach', 'value': 0}, {'label': 'Marketing', 'value': 0}, {'label': 'Ads', 'value': 0}, {'label': 'Hack2skill', 'value': 0}, {'label': 'Other', 'value': 0}],
            'top_domains': [],
            'top_cities': [],
            'top_cities_outside_india': [],
            'top_states': [],
            'country_distribution': [],
            'top_organizations': [],
            'class_stream_distribution': [],
            'designation_distribution': [],
            'occupation_distribution': [],
            'age_groups': [],
            'registration_trends': [],
            'social_media': [],
            'india_state_registrations': [],
            'apac_country_registrations': []
        }
