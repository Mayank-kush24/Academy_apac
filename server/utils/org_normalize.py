"""
Organization name normalization.

Merges messy, inconsistent organization names into canonical forms
for accurate aggregation in dashboard charts.
"""

import re

# Canonical alias map: lowercase key -> canonical display name.
# Add new entries here to merge additional variations.
_ALIAS_MAP = {
    # Tata Consultancy Services
    'tcs': 'Tata Consultancy Services',
    'tata consultancy services': 'Tata Consultancy Services',
    'tata consultancy services limited': 'Tata Consultancy Services',

    # Infosys
    'infosys': 'Infosys',
    'infosys limited': 'Infosys',
    'infosys ltd': 'Infosys',
    'infosys bpo': 'Infosys',

    # Wipro
    'wipro': 'Wipro',
    'wipro limited': 'Wipro',
    'wipro ltd': 'Wipro',

    # Cognizant
    'cognizant': 'Cognizant',
    'cognizant technology solutions': 'Cognizant',
    'cognizant technology solutions corp': 'Cognizant',

    # HCLTech
    'hcltech': 'HCLTech',
    'hcl technologies': 'HCLTech',
    'hcl tech': 'HCLTech',

    # Tech Mahindra
    'tech mahindra': 'Tech Mahindra',
    'tech mahindra ltd': 'Tech Mahindra',
    'tech mahindra limited': 'Tech Mahindra',

    # Accenture
    'accenture': 'Accenture',
    'accenture india': 'Accenture',
    'accenture solutions': 'Accenture',

    # Capgemini
    'capgemini': 'Capgemini',
    'capgemini india': 'Capgemini',
    'capgemini technology services': 'Capgemini',

    # Amazon
    'amazon': 'Amazon',
    'amazon web services': 'Amazon',
    'aws': 'Amazon',
    'amazon development center india pvt limited': 'Amazon',
    'amazon india': 'Amazon',

    # Google
    'google': 'Google',
    'google india': 'Google',
    'google india pvt ltd': 'Google',

    # Microsoft
    'microsoft': 'Microsoft',
    'microsoft india': 'Microsoft',
    'microsoft corporation': 'Microsoft',

    # IBM
    'ibm': 'IBM',
    'ibm india': 'IBM',
    'ibm india pvt ltd': 'IBM',

    # Deloitte
    'deloitte': 'Deloitte',
    'deloitte india': 'Deloitte',
    'deloitte consulting': 'Deloitte',
    'deloitte consulting india pvt ltd': 'Deloitte',
    'deloitte usi': 'Deloitte',

    # SAP
    'sap': 'SAP',
    'sap labs': 'SAP',
    'sap labs india': 'SAP',
    'sap labs india pvt ltd': 'SAP',
    'sap india': 'SAP',

    # Oracle
    'oracle': 'Oracle',
    'oracle india': 'Oracle',
    'oracle india pvt ltd': 'Oracle',

    # Salesforce
    'salesforce': 'Salesforce',
    'salesforce india': 'Salesforce',

    # JP Morgan
    'jp morgan chase': 'JP Morgan Chase',
    'jpmorgan chase': 'JP Morgan Chase',
    'jpmorgan chase and co': 'JP Morgan Chase',
    'jpmorgan chase and co.': 'JP Morgan Chase',
    'jpmorgan': 'JP Morgan Chase',
    'jp morgan': 'JP Morgan Chase',

    # Wells Fargo
    'wells fargo': 'Wells Fargo',

    # HSBC
    'hsbc': 'HSBC',
    'hsbc india': 'HSBC',
    'hsbc technology india': 'HSBC',

    # Dell
    'dell': 'Dell Technologies',
    'dell technologies': 'Dell Technologies',
    'dell india': 'Dell Technologies',

    # Publicis Sapient
    'publicis sapient': 'Publicis Sapient',

    # Genpact
    'genpact': 'Genpact',

    # Ericsson
    'ericsson': 'Ericsson',
    'ericsson india': 'Ericsson',

    # Factspan
    'factspan': 'Factspan Analytics',
    'factspan analytics': 'Factspan Analytics',

    # Harman
    'harman': 'Harman Connected Services',
    'harman connected services': 'Harman Connected Services',

    # DBS
    'dbs bank': 'DBS Bank',
    'dbs': 'DBS Bank',

    # Samsung
    'samsung': 'Samsung',
    'samsung sds': 'Samsung SDS',
    'samsung india': 'Samsung',

    # LTIMindtree
    'ltimindtree': 'LTIMindtree',
    'lti': 'LTIMindtree',
    'l&t infotech': 'LTIMindtree',
    'larsen & toubro infotech': 'LTIMindtree',

    # Amdocs
    'amdocs': 'Amdocs',
    'amdocs development center india': 'Amdocs',
}

# Values to exclude from charts entirely
_EXCLUDE_NAMES = {
    'na', 'n/a', 'none', 'other', 'others', '-', 'nil',
    'freelance', 'freelancer', 'self', 'self employed',
    'not applicable', 'student',
}


def _clean_key(name):
    """Lowercase, strip quotes/whitespace, remove common suffixes."""
    if not name:
        return ''
    s = name.strip().strip('"').strip("'").strip()
    s = s.lower()
    # Remove trailing punctuation
    s = re.sub(r'[.,;]+$', '', s).strip()
    # Remove common legal suffixes for matching
    for suffix in (' pvt ltd', ' pvt. ltd.', ' pvt. ltd', ' private limited',
                   ' india private limited', ' india pvt limited',
                   ' india pvt. ltd.', ' india pvt ltd'):
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
            break
    return s


def normalize_org_name(name):
    """Return the canonical organization name, or None if it should be excluded."""
    if not name or not name.strip():
        return None
    stripped = name.strip().strip('"').strip("'").strip()
    raw_lower = stripped.lower()
    raw_lower = re.sub(r'[.,;]+$', '', raw_lower).strip()
    if not raw_lower or raw_lower in _EXCLUDE_NAMES:
        return None
    # Try full lowercase key first (before suffix stripping)
    canonical = _ALIAS_MAP.get(raw_lower)
    if canonical:
        return canonical
    # Then try with suffix stripped
    key = _clean_key(name)
    if key and key != raw_lower:
        if key in _EXCLUDE_NAMES:
            return None
        canonical = _ALIAS_MAP.get(key)
        if canonical:
            return canonical
    return stripped


# Reverse map: canonical name -> set of alias keys (built once at import time)
_CANONICAL_TO_ALIASES = {}
for _key, _canon in _ALIAS_MAP.items():
    _CANONICAL_TO_ALIASES.setdefault(_canon, set()).add(_key)


def normalize_org_list(raw_names):
    """Deduplicate a list of raw org names into sorted unique canonical names.

    Use this to populate filter dropdowns.
    """
    seen = {}
    for name in raw_names:
        canonical = normalize_org_name(name)
        if canonical and canonical.lower() not in seen:
            seen[canonical.lower()] = canonical
    return sorted(seen.values(), key=str.lower)


def get_org_filter_conditions(column, canonical_names):
    """Build SQLAlchemy OR conditions that match all alias variations of the
    given canonical org names against the provided column.

    Args:
        column: SQLAlchemy column (e.g. UserPIICombined.organization_name)
        canonical_names: list of canonical org names selected by the user

    Returns:
        SQLAlchemy or_() condition, or None if no names provided
    """
    from sqlalchemy import or_
    if not canonical_names:
        return None
    clauses = []
    for name in canonical_names:
        aliases = _CANONICAL_TO_ALIASES.get(name, set())
        if aliases:
            for alias in aliases:
                clauses.append(column.ilike(f'%{alias}%'))
        else:
            clauses.append(column.ilike(f'%{name}%'))
    return or_(*clauses) if clauses else None


def merge_org_counts(rows):
    """Merge a list of (org_name, count) into deduplicated (canonical_name, total_count),
    sorted descending by count.

    Args:
        rows: iterable of (organization_name, count) tuples

    Returns:
        list of {'label': str, 'value': int} dicts, sorted by value desc
    """
    merged = {}
    for raw_name, count in rows:
        canonical = normalize_org_name(raw_name)
        if not canonical:
            continue
        merged[canonical] = merged.get(canonical, 0) + (count or 0)
    result = [{'label': k, 'value': v} for k, v in merged.items()]
    result.sort(key=lambda x: x['value'], reverse=True)
    return result
