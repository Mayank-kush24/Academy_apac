"""
User profiles routes (for viewing user_pii data)
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import or_, and_
from server.models import db, UserPII
from server.utils.auth import get_current_user
from server.utils.permissions import require_role

bp = Blueprint('profiles', __name__)


@bp.route('', methods=['GET'])
@require_role('viewer', 'editor', 'admin')
def get_profiles():
    """Get user profiles with search and filters"""
    try:
        # Get query parameters
        search = request.args.get('search', '').strip()
        organization = request.args.get('organization', '').strip()
        domain = request.args.get('domain', '').strip()
        country = request.args.get('country', '').strip()
        state = request.args.get('state', '').strip()
        city = request.args.get('city', '').strip()
        gender = request.args.get('gender', '').strip()
        class_stream = request.args.get('class_stream', '').strip()
        designation = request.args.get('designation', '').strip()
        occupation = request.args.get('occupation', '').strip()
        has_github = request.args.get('has_github', '').strip()
        has_linkedin = request.args.get('has_linkedin', '').strip()
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)  # Max 100 per page
        
        # Start building query
        query = UserPII.query
        
        # Search filter (searches in name, email, organization)
        if search:
            search_filter = or_(
                UserPII.name.ilike(f'%{search}%'),
                UserPII.email.ilike(f'%{search}%'),
                UserPII.organization_name.ilike(f'%{search}%'),
                UserPII.designation.ilike(f'%{search}%'),
                UserPII.occupation.ilike(f'%{search}%')
            )
            query = query.filter(search_filter)
        
        # Organization filter
        if organization:
            query = query.filter(UserPII.organization_name.ilike(f'%{organization}%'))
        
        # Domain filter
        if domain:
            query = query.filter(UserPII.domain.ilike(f'%{domain}%'))
        
        # Country filter
        if country:
            query = query.filter(UserPII.country.ilike(f'%{country}%'))
        
        # State filter
        if state:
            query = query.filter(UserPII.state.ilike(f'%{state}%'))
        
        # City filter
        if city:
            query = query.filter(UserPII.city.ilike(f'%{city}%'))
        
        # Gender filter
        if gender:
            query = query.filter(UserPII.gender.ilike(f'%{gender}%'))
        
        # Class stream filter
        if class_stream:
            query = query.filter(UserPII.class_stream.ilike(f'%{class_stream}%'))
        
        # Designation filter
        if designation:
            query = query.filter(UserPII.designation.ilike(f'%{designation}%'))
        
        # Occupation filter
        if occupation:
            query = query.filter(UserPII.occupation.ilike(f'%{occupation}%'))
        
        # GitHub filter
        if has_github.lower() == 'true':
            query = query.filter(
                UserPII.github_url.isnot(None),
                UserPII.github_url != ''
            )
        elif has_github.lower() == 'false':
            query = query.filter(
                or_(
                    UserPII.github_url.is_(None),
                    UserPII.github_url == ''
                )
            )
        
        # LinkedIn filter
        if has_linkedin.lower() == 'true':
            query = query.filter(
                UserPII.linkedin_url.isnot(None),
                UserPII.linkedin_url != ''
            )
        elif has_linkedin.lower() == 'false':
            query = query.filter(
                or_(
                    UserPII.linkedin_url.is_(None),
                    UserPII.linkedin_url == ''
                )
            )
        
        # Get total count before pagination - use efficient count
        # For large datasets, use estimate if available, otherwise use count
        try:
            # Try to use a more efficient count query
            total = db.session.query(func.count(UserPII.id)).select_from(query.subquery()).scalar()
        except:
            # Fallback to regular count
            total = query.count()
        
        # Apply pagination
        pagination = query.order_by(UserPII.created_at.desc()).paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        profiles = [profile.to_dict() for profile in pagination.items]
        
        return jsonify({
            'profiles': profiles,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/filters', methods=['GET'])
@require_role('viewer', 'editor', 'admin')
def get_filter_options():
    """Get available filter options for dropdowns (cached)"""
    from server.utils.cache import cache_result
    
    @cache_result(ttl=600)  # Cache for 10 minutes
    def _get_filter_options():
        """Internal function to fetch filter options"""
        # Get distinct values for filters - limit to top 1000 for performance
        organizations = db.session.query(UserPII.organization_name).filter(
            UserPII.organization_name.isnot(None),
            UserPII.organization_name != ''
        ).distinct().order_by(UserPII.organization_name).limit(1000).all()
        
        domains = db.session.query(UserPII.domain).filter(
            UserPII.domain.isnot(None),
            UserPII.domain != ''
        ).distinct().order_by(UserPII.domain).limit(1000).all()
        
        countries = db.session.query(UserPII.country).filter(
            UserPII.country.isnot(None),
            UserPII.country != ''
        ).distinct().order_by(UserPII.country).limit(1000).all()
        
        states = db.session.query(UserPII.state).filter(
            UserPII.state.isnot(None),
            UserPII.state != ''
        ).distinct().order_by(UserPII.state).limit(1000).all()
        
        cities = db.session.query(UserPII.city).filter(
            UserPII.city.isnot(None),
            UserPII.city != ''
        ).distinct().order_by(UserPII.city).limit(1000).all()
        
        genders = db.session.query(UserPII.gender).filter(
            UserPII.gender.isnot(None),
            UserPII.gender != ''
        ).distinct().order_by(UserPII.gender).limit(100).all()
        
        class_streams = db.session.query(UserPII.class_stream).filter(
            UserPII.class_stream.isnot(None),
            UserPII.class_stream != ''
        ).distinct().order_by(UserPII.class_stream).limit(1000).all()
        
        designations = db.session.query(UserPII.designation).filter(
            UserPII.designation.isnot(None),
            UserPII.designation != ''
        ).distinct().order_by(UserPII.designation).limit(1000).all()
        
        occupations = db.session.query(UserPII.occupation).filter(
            UserPII.occupation.isnot(None),
            UserPII.occupation != ''
        ).distinct().order_by(UserPII.occupation).limit(1000).all()
        
        return {
            'organizations': [o[0] for o in organizations],
            'domains': [d[0] for d in domains],
            'countries': [c[0] for c in countries],
            'states': [s[0] for s in states],
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
@require_role('viewer', 'editor', 'admin')
def get_profile_detail(profile_id):
    """Get detailed profile information"""
    try:
        profile = UserPII.query.filter_by(id=profile_id).first()
        if not profile:
            return jsonify({'error': 'Profile not found'}), 404
        
        return jsonify({
            'profile': profile.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
