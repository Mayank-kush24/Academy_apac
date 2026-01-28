"""
Dashboard analytics routes
"""
from flask import Blueprint, jsonify, request
from sqlalchemy import func, desc, case
from datetime import datetime, timedelta
from server.models import db, UserPII
from server.utils.auth import get_current_user
from server.utils.permissions import require_role
from server.utils.cache import cache_result

bp = Blueprint('dashboard', __name__)


@bp.route('/summary', methods=['GET'])
@require_role('viewer', 'editor', 'admin')
def get_summary():
    """Get dashboard summary statistics (cached)"""
    from server.utils.cache import cache_result
    
    @cache_result(ttl=300)  # Cache for 5 minutes
    def _get_summary(period):
        """Internal function to fetch summary (cached)"""
        return _fetch_summary_data(period)
    
    try:
        period = request.args.get('period', '30d')
        result = _get_summary(period)
        return jsonify(result), 200
    except Exception as e:
        # Return empty data instead of error
        return jsonify({
            'total_users': 0,
            'unique_organizations': 0,
            'top_domain': 'N/A',
            'top_city': 'N/A'
        }), 200


def _fetch_summary_data(period):
    """Internal function to fetch summary data"""
    try:
        # Get period parameter (7d, 30d, 90d, or None for all)
        period = request.args.get('period', '30d')
        days = None
        if period == '7d':
            days = 7
        elif period == '30d':
            days = 30
        elif period == '90d':
            days = 90
        
        # Base query with optional date filter
        base_query = UserPII.query
        cutoff_date = None
        if days:
            cutoff_date = datetime.now() - timedelta(days=days)
            base_query = base_query.filter(UserPII.created_at >= cutoff_date)
        
        # Total users
        total_users = base_query.count() or 0
        
        # Unique organizations
        try:
            org_query = db.session.query(func.count(func.distinct(UserPII.organization_name)))
            if cutoff_date:
                org_query = org_query.filter(UserPII.created_at >= cutoff_date)
            unique_orgs = org_query.scalar() or 0
        except:
            unique_orgs = 0
        
        # Top domain
        top_domain = None
        try:
            domain_query = db.session.query(
                UserPII.domain,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.domain.isnot(None),
                UserPII.domain != ''
            )
            if cutoff_date:
                domain_query = domain_query.filter(UserPII.created_at >= cutoff_date)
            top_domain_result = domain_query.group_by(
                UserPII.domain
            ).order_by(desc('count')).first()
            
            top_domain = top_domain_result[0] if top_domain_result else None
        except:
            top_domain = None
        
        # Top city
        top_city = None
        try:
            city_query = db.session.query(
                UserPII.city,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.city.isnot(None),
                UserPII.city != ''
            )
            if cutoff_date:
                city_query = city_query.filter(UserPII.created_at >= cutoff_date)
            top_city_result = city_query.group_by(
                UserPII.city
            ).order_by(desc('count')).first()
            
            top_city = top_city_result[0] if top_city_result else None
        except:
            top_city = None
        
        # Additional stats
        # Total countries
        try:
            unique_countries = db.session.query(func.count(func.distinct(UserPII.country))).filter(
                UserPII.country.isnot(None),
                UserPII.country != ''
            ).scalar() or 0
        except:
            unique_countries = 0
        
        # Users with GitHub
        try:
            github_query = UserPII.query.filter(
                UserPII.github_url.isnot(None),
                UserPII.github_url != ''
            )
            if cutoff_date:
                github_query = github_query.filter(UserPII.created_at >= cutoff_date)
            users_with_github = github_query.count() or 0
        except:
            users_with_github = 0
        
        # Users with LinkedIn
        try:
            linkedin_query = UserPII.query.filter(
                UserPII.linkedin_url.isnot(None),
                UserPII.linkedin_url != ''
            )
            if cutoff_date:
                linkedin_query = linkedin_query.filter(UserPII.created_at >= cutoff_date)
            users_with_linkedin = linkedin_query.count() or 0
        except:
            users_with_linkedin = 0
        
        # Top organization
        top_org = None
        try:
            org_query = db.session.query(
                UserPII.organization_name,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.organization_name.isnot(None),
                UserPII.organization_name != ''
            )
            if cutoff_date:
                org_query = org_query.filter(UserPII.created_at >= cutoff_date)
            top_org_result = org_query.group_by(
                UserPII.organization_name
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
                    func.extract('year', func.age(today, UserPII.date_of_birth))
                )
            ).filter(
                UserPII.date_of_birth.isnot(None)
            )
            if days:
                cutoff_date = datetime.now() - timedelta(days=days)
                age_query = age_query.filter(UserPII.created_at >= cutoff_date)
            
            avg_age_result = age_query.scalar()
            if avg_age_result:
                avg_age = int(avg_age_result)
        except Exception as e:
            # Fallback to Python calculation if SQL fails
            try:
                today = datetime.now().date()
                dob_query = UserPII.query.filter(
                    UserPII.date_of_birth.isnot(None)
                )
                if days:
                    cutoff_date = datetime.now() - timedelta(days=days)
                    dob_query = dob_query.filter(UserPII.created_at >= cutoff_date)
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
        
        return {
            'total_users': total_users,
            'unique_organizations': unique_orgs,
            'unique_countries': unique_countries,
            'top_domain': top_domain or 'N/A',
            'top_city': top_city or 'N/A',
            'top_organization': top_org or 'N/A',
            'users_with_github': users_with_github,
            'users_with_linkedin': users_with_linkedin,
            'average_age': avg_age
        }
    except Exception as e:
        # Return empty data instead of error
        return {
            'total_users': 0,
            'unique_organizations': 0,
            'top_domain': 'N/A',
            'top_city': 'N/A'
        }


@bp.route('/widget-stats', methods=['GET'])
@require_role('viewer', 'editor', 'admin')
def get_widget_stats():
    """Get lightweight stats for iOS widget"""
    try:
        # Get today's signups
        today = datetime.now().date()
        today_signups = UserPII.query.filter(
            func.date(UserPII.registered_at) == today
        ).count() or 0
        
        # Get total users
        total_users = UserPII.query.count() or 0
        
        # Get active users (registered in last 30 days)
        active_cutoff = datetime.now() - timedelta(days=30)
        active_users = UserPII.query.filter(
            UserPII.registered_at >= active_cutoff
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
@require_role('viewer', 'editor', 'admin')
def get_charts():
    """Get chart data for dashboard (cached)"""
    from server.utils.cache import cache_result
    
    @cache_result(ttl=300)  # Cache for 5 minutes
    def _get_charts(period):
        """Internal function to fetch charts (cached)"""
        return _fetch_charts_data(period)
    
    try:
        period = request.args.get('period', '30d')
        result = _get_charts(period)
        return jsonify(result), 200
    except Exception as e:
        # Return empty data instead of error
        return jsonify({
            'gender_distribution': [],
            'top_domains': [],
            'top_cities': [],
            'top_states': [],
            'country_distribution': [],
            'top_organizations': [],
            'class_stream_distribution': [],
            'designation_distribution': [],
            'occupation_distribution': [],
            'age_groups': [],
            'registration_trends': [],
            'social_media': []
        }), 200


def _fetch_charts_data(period):
    """Internal function to fetch charts data"""
    try:
        # Get period parameter (7d, 30d, 90d, or None for all)
        period = request.args.get('period', '30d')
        days = None
        if period == '7d':
            days = 7
        elif period == '30d':
            days = 30
        elif period == '90d':
            days = 90
        
        # Base query with optional date filter
        base_query = UserPII.query
        cutoff_date = None
        if days:
            cutoff_date = datetime.now() - timedelta(days=days)
            base_query = base_query.filter(UserPII.created_at >= cutoff_date)
        
        # Gender distribution
        gender_distribution = []
        try:
            gender_query = db.session.query(
                UserPII.gender,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.gender.isnot(None),
                UserPII.gender != ''
            )
            if cutoff_date:
                gender_query = gender_query.filter(UserPII.created_at >= cutoff_date)
            gender_data = gender_query.group_by(
                UserPII.gender
            ).all()
            gender_distribution = [{'label': g[0], 'value': g[1]} for g in gender_data]
        except:
            gender_distribution = []
        
        # Top domains (top 10)
        top_domains_data = []
        try:
            domains_query = db.session.query(
                UserPII.domain,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.domain.isnot(None),
                UserPII.domain != ''
            )
            if cutoff_date:
                domains_query = domains_query.filter(UserPII.created_at >= cutoff_date)
            top_domains = domains_query.group_by(
                UserPII.domain
            ).order_by(desc('count')).limit(10).all()
            top_domains_data = [{'label': d[0], 'value': d[1]} for d in top_domains]
        except:
            top_domains_data = []
        
        # Top cities (top 10)
        top_cities_data = []
        try:
            cities_query = db.session.query(
                UserPII.city,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.city.isnot(None),
                UserPII.city != ''
            )
            if cutoff_date:
                cities_query = cities_query.filter(UserPII.created_at >= cutoff_date)
            top_cities = cities_query.group_by(
                UserPII.city
            ).order_by(desc('count')).limit(10).all()
            top_cities_data = [{'label': c[0], 'value': c[1]} for c in top_cities]
        except:
            top_cities_data = []
        
        # Top states (top 10)
        top_states_data = []
        try:
            states_query = db.session.query(
                UserPII.state,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.state.isnot(None),
                UserPII.state != ''
            )
            if cutoff_date:
                states_query = states_query.filter(UserPII.created_at >= cutoff_date)
            top_states = states_query.group_by(
                UserPII.state
            ).order_by(desc('count')).limit(10).all()
            top_states_data = [{'label': s[0], 'value': s[1]} for s in top_states]
        except:
            top_states_data = []
        
        # Country distribution
        country_distribution = []
        try:
            countries_query = db.session.query(
                UserPII.country,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.country.isnot(None),
                UserPII.country != ''
            )
            if cutoff_date:
                countries_query = countries_query.filter(UserPII.created_at >= cutoff_date)
            countries = countries_query.group_by(
                UserPII.country
            ).order_by(desc('count')).limit(10).all()
            country_distribution = [{'label': c[0], 'value': c[1]} for c in countries]
        except:
            country_distribution = []
        
        # Top organizations (top 10)
        top_organizations_data = []
        try:
            orgs_query = db.session.query(
                UserPII.organization_name,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.organization_name.isnot(None),
                UserPII.organization_name != ''
            )
            if cutoff_date:
                orgs_query = orgs_query.filter(UserPII.created_at >= cutoff_date)
            top_orgs = orgs_query.group_by(
                UserPII.organization_name
            ).order_by(desc('count')).limit(10).all()
            top_organizations_data = [{'label': o[0], 'value': o[1]} for o in top_orgs]
        except:
            top_organizations_data = []
        
        # Class stream distribution
        class_stream_data = []
        try:
            streams_query = db.session.query(
                UserPII.class_stream,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.class_stream.isnot(None),
                UserPII.class_stream != ''
            )
            if cutoff_date:
                streams_query = streams_query.filter(UserPII.created_at >= cutoff_date)
            streams = streams_query.group_by(
                UserPII.class_stream
            ).order_by(desc('count')).all()
            class_stream_data = [{'label': s[0], 'value': s[1]} for s in streams]
        except:
            class_stream_data = []
        
        # Designation distribution (top 10)
        designation_data = []
        try:
            designation_query = db.session.query(
                UserPII.designation,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.designation.isnot(None),
                UserPII.designation != ''
            )
            if cutoff_date:
                designation_query = designation_query.filter(UserPII.created_at >= cutoff_date)
            designations = designation_query.group_by(
                UserPII.designation
            ).order_by(desc('count')).limit(10).all()
            designation_data = [{'label': d[0], 'value': d[1]} for d in designations]
        except:
            designation_data = []
        
        # Top occupations (top 10)
        occupation_data = []
        try:
            occupation_query = db.session.query(
                UserPII.occupation,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.occupation.isnot(None),
                UserPII.occupation != ''
            )
            if cutoff_date:
                occupation_query = occupation_query.filter(UserPII.created_at >= cutoff_date)
            occupations = occupation_query.group_by(
                UserPII.occupation
            ).order_by(desc('count')).limit(10).all()
            occupation_data = [{'label': o[0], 'value': o[1]} for o in occupations]
        except:
            occupation_data = []
        
        # Age groups distribution - Optimized using SQL CASE statements
        age_groups_data = []
        try:
            today = datetime.now().date()
            
            # Use SQL CASE to calculate age groups directly in database
            age_expr = func.extract('year', func.age(today, UserPII.date_of_birth))
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
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.date_of_birth.isnot(None),
                age_expr >= 18  # Only count adults
            )
            if days:
                cutoff_date = datetime.now() - timedelta(days=days)
                age_query = age_query.filter(UserPII.created_at >= cutoff_date)
            
            age_results = age_query.group_by(age_group_expr).all()
            age_groups_data = [{'label': r[0], 'value': r[1]} for r in age_results if r[0] is not None]
        except Exception as e:
            # Fallback to Python calculation if SQL fails
            try:
                print(f"SQL age calculation failed, using fallback: {e}")
                today = datetime.now().date()
                dob_query = UserPII.query.filter(
                    UserPII.date_of_birth.isnot(None)
                )
                if days:
                    cutoff_date = datetime.now() - timedelta(days=days)
                    dob_query = dob_query.filter(UserPII.created_at >= cutoff_date)
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
            # Use period days or default to 30
            trend_days = days if days else 30
            start_date = datetime.now() - timedelta(days=trend_days)
            # Use date_trunc for PostgreSQL compatibility, filter out NULL registered_at
            trends = db.session.query(
                func.date_trunc('day', UserPII.registered_at).label('date'),
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.registered_at.isnot(None),
                UserPII.registered_at >= start_date
            ).group_by(
                func.date_trunc('day', UserPII.registered_at)
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
            github_query = UserPII.query.filter(
                UserPII.github_url.isnot(None),
                UserPII.github_url != ''
            )
            if cutoff_date:
                github_query = github_query.filter(UserPII.created_at >= cutoff_date)
            github_count = github_query.count() or 0
            
            linkedin_query = UserPII.query.filter(
                UserPII.linkedin_url.isnot(None),
                UserPII.linkedin_url != ''
            )
            if cutoff_date:
                linkedin_query = linkedin_query.filter(UserPII.created_at >= cutoff_date)
            linkedin_count = linkedin_query.count() or 0
            
            both_query = UserPII.query.filter(
                UserPII.github_url.isnot(None),
                UserPII.github_url != '',
                UserPII.linkedin_url.isnot(None),
                UserPII.linkedin_url != ''
            )
            if cutoff_date:
                both_query = both_query.filter(UserPII.created_at >= cutoff_date)
            both_count = both_query.count() or 0
            
            # Get total for period
            period_total = base_query.count() if days else UserPII.query.count()
            
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
        
        return {
            'gender_distribution': gender_distribution,
            'top_domains': top_domains_data,
            'top_cities': top_cities_data,
            'top_states': top_states_data,
            'country_distribution': country_distribution,
            'top_organizations': top_organizations_data,
            'class_stream_distribution': class_stream_data,
            'designation_distribution': designation_data,
            'occupation_distribution': occupation_data,
            'age_groups': age_groups_data,
            'registration_trends': registration_trends,
            'social_media': social_media_data
        }
    except Exception as e:
        # Return empty data instead of error
        return {
            'gender_distribution': [],
            'top_domains': [],
            'top_cities': [],
            'top_states': [],
            'country_distribution': [],
            'top_organizations': [],
            'class_stream_distribution': [],
            'designation_distribution': [],
            'occupation_distribution': [],
            'age_groups': [],
            'registration_trends': [],
            'social_media': []
        }
