"""
Industry ↔ Domain mapping used by dashboard segmentation and table pages.
"""
from collections import defaultdict

INDUSTRY_DOMAIN_MAP = {
    'Technology': [
        'Software development', 'Software Development',
        'Information Technology', 'FinTech', 'Fintech',
        'Cloud Computing', 'DevOps', 'Cybersecurity',
        'Web Development', 'Mobile Development', 'IT Services',
        'SaaS', 'Blockchain', 'IoT',
        'Technology', 'Tech', 'IT',
    ],
    'Data & AI': [
        'Artificial Intelligence', 'Data Analytics', 'Data Science',
        'Machine Learning', 'Deep Learning', 'Big Data',
        'Business Intelligence', 'Natural Language Processing', 'NLP',
        'Computer Vision', 'Generative AI', 'Gen AI',
        'Data Engineering', 'Data', 'AI', 'Analytics',
    ],
    'Business & Commerce': [
        'E-Commerce', 'E-commerce', 'Marketing & Advertising',
        'Marketing', 'Advertising', 'Sales', 'Retail',
        'Business Development', 'Consulting', 'Management',
        'Finance', 'Banking', 'Insurance', 'Real Estate',
        'Accounting', 'Human Resources', 'HR', 'Operations',
        'Supply Chain', 'Logistics', 'Business',
    ],
    'Manufacturing & Engineering': [
        'Manufacturing', 'Engineering', 'Automotive',
        'Aerospace', 'Electronics', 'Hardware',
        'Construction', 'Energy', 'Oil & Gas',
        'Mechanical', 'Civil Engineering', 'Electrical',
        'Chemical', 'Industrial',
    ],
    'Education & Research': [
        'Education & Skill Development', 'Education', 'Academia',
        'Research', 'Training', 'EdTech', 'E-Learning',
        'Teaching', 'Academic',
    ],
    'Healthcare & Life Sciences': [
        'Healthcare', 'Health', 'Pharma', 'Pharmaceutical',
        'Biotechnology', 'Medical', 'Life Sciences',
        'Hospital', 'Clinical', 'Nursing',
    ],
    'Media & Design': [
        'Media', 'Entertainment', 'Gaming', 'Design',
        'UI/UX', 'Graphic Design', 'Content Creation',
        'Film', 'Music', 'Animation', 'Creative',
    ],
    'Government & Public Sector': [
        'Government', 'Public Sector', 'Defense', 'Defence',
        'Military', 'Non-Profit', 'NGO', 'Social',
    ],
    'Telecom': [
        'Telecommunications', 'Telecom', 'Networking',
    ],
}

_EXTRA_DOMAIN_MAPPINGS = {
    # Media & Design
    'media & entertainment': 'Media & Design',
    'heritage & culture': 'Media & Design',
    # Healthcare & Life Sciences
    'healthcare & medical services': 'Healthcare & Life Sciences',
    'healthtech': 'Healthcare & Life Sciences',
    'medtech': 'Healthcare & Life Sciences',
    'biomedical engineering': 'Healthcare & Life Sciences',
    'biotechnology and life sciences': 'Healthcare & Life Sciences',
    'genetic engineering': 'Healthcare & Life Sciences',
    'pharmaceuticals': 'Healthcare & Life Sciences',
    'fitness & sports': 'Healthcare & Life Sciences',
    # Business & Commerce
    'financial services': 'Business & Commerce',
    'finance & insurance': 'Business & Commerce',
    'social media marketing': 'Business & Commerce',
    'food & beverage': 'Business & Commerce',
    'fashion & apparel': 'Business & Commerce',
    'travel & tourism': 'Business & Commerce',
    'transportation & logistics': 'Business & Commerce',
    'hospitality': 'Business & Commerce',
    'legal and governance': 'Business & Commerce',
    # Technology
    'mobile apps': 'Technology',
    'emerging technologies': 'Technology',
    'social networking': 'Technology',
    'robotics': 'Technology',
    'augmented reality (ar)': 'Technology',
    'quantum computing': 'Technology',
    'agritech': 'Technology',
    'autonomous vehicles': 'Technology',
    '3d printing': 'Technology',
    'drones & unmanned aerial vehicles': 'Technology',
    'clean & green technology': 'Technology',
    'wearable technology': 'Technology',
    'smart cities': 'Technology',
    'smart grids': 'Technology',
    'water technology': 'Technology',
    'mobile payments': 'Technology',
    'metaverse': 'Technology',
    # Manufacturing & Engineering
    'sustainable development': 'Manufacturing & Engineering',
    'environmental solutions': 'Manufacturing & Engineering',
    'construction & real estate': 'Manufacturing & Engineering',
    'mining': 'Manufacturing & Engineering',
    'industrial automation': 'Manufacturing & Engineering',
    'infrastructure development': 'Manufacturing & Engineering',
    'infrastructure & transportation': 'Manufacturing & Engineering',
    'renewable energy': 'Manufacturing & Engineering',
    'agriculture': 'Manufacturing & Engineering',
    'waste management': 'Manufacturing & Engineering',
    'industrial safety': 'Manufacturing & Engineering',
    'electric vehicles': 'Manufacturing & Engineering',
    'recycling': 'Manufacturing & Engineering',
    # Education & Research
    'research & innovation': 'Education & Research',
    # Government & Public Sector
    'non-profit organizations': 'Government & Public Sector',
    'rural development': 'Government & Public Sector',
    'vertex pulse.com': 'Other',
}

_DOMAIN_INDUSTRY_LOOKUP = {}
for _industry, _domains in INDUSTRY_DOMAIN_MAP.items():
    for _d in _domains:
        _DOMAIN_INDUSTRY_LOOKUP[_d.strip().lower()] = _industry
_DOMAIN_INDUSTRY_LOOKUP.update(_EXTRA_DOMAIN_MAPPINGS)

# Keyword → industry for inferring from free-text designation field.
# Order matters: first match wins. More specific keywords come first.
_DESIGNATION_KEYWORDS = [
    # Technology
    ('sde', 'Technology'),
    ('swe', 'Technology'),
    ('tech intern', 'Technology'),
    ('software', 'Technology'),
    ('developer', 'Technology'),
    ('full stack', 'Technology'),
    ('fullstack', 'Technology'),
    ('front end', 'Technology'),
    ('frontend', 'Technology'),
    ('back end', 'Technology'),
    ('backend', 'Technology'),
    ('programmer', 'Technology'),
    ('coder', 'Technology'),
    ('engineer', 'Technology'),
    ('devops', 'Technology'),
    ('sre', 'Technology'),
    ('cloud', 'Technology'),
    ('sysadmin', 'Technology'),
    ('system admin', 'Technology'),
    ('network admin', 'Technology'),
    ('web dev', 'Technology'),
    ('mobile dev', 'Technology'),
    ('ios dev', 'Technology'),
    ('android dev', 'Technology'),
    ('qa', 'Technology'),
    ('test engineer', 'Technology'),
    ('tester', 'Technology'),
    ('automation', 'Technology'),
    ('architect', 'Technology'),
    ('tech lead', 'Technology'),
    ('technical lead', 'Technology'),
    ('scrum', 'Technology'),
    ('agile', 'Technology'),
    ('cybersecurity', 'Technology'),
    ('security analyst', 'Technology'),
    ('it ', 'Technology'),
    ('information technology', 'Technology'),
    ('blockchain', 'Technology'),
    ('embedded', 'Technology'),
    ('firmware', 'Technology'),
    # Data & AI
    ('data scientist', 'Data & AI'),
    ('data engineer', 'Data & AI'),
    ('data analyst', 'Data & AI'),
    ('machine learning', 'Data & AI'),
    ('ml engineer', 'Data & AI'),
    ('ai ', 'Data & AI'),
    ('artificial intelligence', 'Data & AI'),
    ('deep learning', 'Data & AI'),
    ('nlp', 'Data & AI'),
    ('computer vision', 'Data & AI'),
    ('big data', 'Data & AI'),
    ('analytics', 'Data & AI'),
    ('bi developer', 'Data & AI'),
    ('bi analyst', 'Data & AI'),
    # Business & Commerce
    ('marketing', 'Business & Commerce'),
    ('sales', 'Business & Commerce'),
    ('business analyst', 'Business & Commerce'),
    ('business develop', 'Business & Commerce'),
    ('product manager', 'Business & Commerce'),
    ('project manager', 'Business & Commerce'),
    ('consultant', 'Business & Commerce'),
    ('finance', 'Business & Commerce'),
    ('accountant', 'Business & Commerce'),
    ('auditor', 'Business & Commerce'),
    ('banker', 'Business & Commerce'),
    ('hr ', 'Business & Commerce'),
    ('human resource', 'Business & Commerce'),
    ('recruiter', 'Business & Commerce'),
    ('operations', 'Business & Commerce'),
    ('supply chain', 'Business & Commerce'),
    ('logistics', 'Business & Commerce'),
    ('procurement', 'Business & Commerce'),
    ('retail', 'Business & Commerce'),
    ('manager', 'Business & Commerce'),
    ('executive', 'Business & Commerce'),
    ('director', 'Business & Commerce'),
    ('ceo', 'Business & Commerce'),
    ('cto', 'Technology'),
    ('cfo', 'Business & Commerce'),
    ('coo', 'Business & Commerce'),
    ('vp ', 'Business & Commerce'),
    ('founder', 'Business & Commerce'),
    ('entrepreneur', 'Business & Commerce'),
    # Manufacturing & Engineering
    ('mechanical', 'Manufacturing & Engineering'),
    ('civil', 'Manufacturing & Engineering'),
    ('electrical', 'Manufacturing & Engineering'),
    ('manufacturing', 'Manufacturing & Engineering'),
    ('production', 'Manufacturing & Engineering'),
    ('automotive', 'Manufacturing & Engineering'),
    ('chemical', 'Manufacturing & Engineering'),
    # Education & Research
    ('professor', 'Education & Research'),
    ('teacher', 'Education & Research'),
    ('lecturer', 'Education & Research'),
    ('researcher', 'Education & Research'),
    ('instructor', 'Education & Research'),
    ('trainer', 'Education & Research'),
    ('faculty', 'Education & Research'),
    ('educator', 'Education & Research'),
    ('academic', 'Education & Research'),
    # Healthcare & Life Sciences
    ('doctor', 'Healthcare & Life Sciences'),
    ('nurse', 'Healthcare & Life Sciences'),
    ('physician', 'Healthcare & Life Sciences'),
    ('pharmacist', 'Healthcare & Life Sciences'),
    ('medical', 'Healthcare & Life Sciences'),
    ('clinical', 'Healthcare & Life Sciences'),
    ('biotech', 'Healthcare & Life Sciences'),
    ('health', 'Healthcare & Life Sciences'),
    # Media & Design
    ('designer', 'Media & Design'),
    ('graphic', 'Media & Design'),
    ('ui', 'Media & Design'),
    ('ux', 'Media & Design'),
    ('creative', 'Media & Design'),
    ('content', 'Media & Design'),
    ('journalist', 'Media & Design'),
    ('editor', 'Media & Design'),
    ('animator', 'Media & Design'),
    ('photographer', 'Media & Design'),
    ('videographer', 'Media & Design'),
    # Government
    ('government', 'Government & Public Sector'),
    ('civil servant', 'Government & Public Sector'),
    # Telecom
    ('telecom', 'Telecom'),
]


def _infer_from_designation(designation):
    """Try to infer industry from a free-text designation string."""
    if not designation:
        return ''
    low = designation.lower()
    for keyword, industry in _DESIGNATION_KEYWORDS:
        if keyword in low:
            return industry
    return ''


# Known IT-services / tech companies (lowercase).
_TECH_ORGS = {
    'accenture', 'accenture india', 'accentue',
    'infosys', 'infosys limited', 'wipro', 'tcs',
    'tata consultancy services', 'cognizant', 'cognizant technology solutions',
    'hcltech', 'hcl technologies', 'tech mahindra', 'capgemini',
    'mindtree', 'mphasis', 'l&t infotech', 'lti', 'ltimindtree',
    'persistent systems', 'zensar', 'hexaware', 'cyient', 'niit',
    'oracle', 'google', 'microsoft', 'amazon', 'meta', 'apple',
    'ibm', 'samsung', 'sap', 'adobe', 'salesforce', 'cisco',
    'intel', 'qualcomm', 'nvidia', 'vmware', 'dell', 'hp',
    'zoho', 'zoho corporation', 'freshworks', 'razorpay', 'paytm', 'flipkart',
    'swiggy', 'zomato', 'ola', 'byjus', 'mu sigma', 'thoughtworks',
    'atlassian', 'uber', 'grab', 'shopee', 'gojek', 'tokopedia',
    'publicis sapient', 'factspan analytics', 'factspan',
    'amazon development center india pvt limited',
    'dxc technology', 'dxc', 'epam', 'epam systems',
    'synechron', 'globant', 'nagarro', 'amdocs', 'virtusa',
    'cgi', 'coforge', 'sonata software', 'birlasoft',
    'atos', 'ntt data', 'fujitsu', 'hitachi',
    'paypal', 'stripe', 'twilio', 'datadog', 'snowflake',
    'servicenow', 'workday', 'splunk', 'elastic',
    'tata elxsi', 'larsen & toubro infotech',
    'juspay', 'cred', 'meesho', 'phonepe', 'groww',
    'tekion', 'sprinklr', 'browserstack',
    'genpact', 'expedia group', 'expedia',
    'taskus', 'taskus india private limited',
    'natwest group', 'natwest',
    'pt telkom indonesia', 'telkom indonesia',
    'wipro limited',
}

# Consulting / finance firms.
_BIZ_ORGS = {
    'deloitte', 'pwc', 'pwc india', 'ey', 'ernst & young', 'kpmg',
    'mckinsey', 'bcg', 'bain', 'goldman sachs', 'jp morgan',
    'jp morgan chase', 'morgan stanley', 'hsbc', 'barclays', 'citi', 'citibank',
    'deutsche bank', 'ubs', 'credit suisse', 'icici', 'hdfc',
    'axis bank', 'kotak', 'sbi', 'rbi',
    'wells fargo', 'american express', 'amex',
    'american express (india) private limited',
    'bank of america', 'standard chartered', 'nomura',
    'mastercard', 'visa',
    'pwc acceleration centre', 'pwc acceleration center',
    'deloitte usi', 'citi corp', 'citicorp',
    'zs associates', 'zs', 'nielseniq', 'nielsen',
    'concentrix', 'concentrix daksh services india private limited',
    'pricewaterhousecoopers services llp', 'pricewaterhousecoopers',
    'jpmorgan chase and co.', 'jpmorgan chase', 'jpmorgan',
    'deutsche india private limited', 'deutsche',
}

# Organization keyword → industry (first match wins).
_ORG_KEYWORDS = [
    # Education indicators (including common misspellings)
    ('university', 'Education & Research'),
    ('universitas', 'Education & Research'),
    ('institute', 'Education & Research'),
    ('institue', 'Education & Research'),
    ('insitute', 'Education & Research'),
    ('institut', 'Education & Research'),
    ('college', 'Education & Research'),
    ('collage', 'Education & Research'),
    ('school', 'Education & Research'),
    ('academy', 'Education & Research'),
    ('iit ', 'Education & Research'),
    ('iit-', 'Education & Research'),
    ('nit ', 'Education & Research'),
    ('iiit', 'Education & Research'),
    ('bits ', 'Education & Research'),
    ('ignou', 'Education & Research'),
    ('lnmiit', 'Education & Research'),
    ('polytechnic', 'Education & Research'),
    ('vidyalaya', 'Education & Research'),
    ('vidyapeeth', 'Education & Research'),
    ('vikas', 'Education & Research'),
    ('engineering', 'Education & Research'),
    ('campus', 'Education & Research'),
    ('education', 'Education & Research'),
    ('vit ', 'Education & Research'),
    ('srm ', 'Education & Research'),
    ('univeristy', 'Education & Research'),
    ('unisversity', 'Education & Research'),
    ('univerity', 'Education & Research'),
    ('institude', 'Education & Research'),
    ('insistute', 'Education & Research'),
    ('incstitute', 'Education & Research'),
    ('vidhyapeetham', 'Education & Research'),
    ('vidyapeetham', 'Education & Research'),
    ('anusandhan', 'Education & Research'),
    ('siksha', 'Education & Research'),
    ('upes', 'Education & Research'),
    ('lnct', 'Education & Research'),
    ('cmrit', 'Education & Research'),
    ('bvrit', 'Education & Research'),
    ('univerisity', 'Education & Research'),
    ('unersity', 'Education & Research'),
    ('instituition', 'Education & Research'),
    ('institiute', 'Education & Research'),
    ('vidyapith', 'Education & Research'),
    ('nmims', 'Education & Research'),
    ('jamia', 'Education & Research'),
    ('sistec', 'Education & Research'),
    ('techno main', 'Education & Research'),
    ('techno international', 'Education & Research'),
    ('mit wpu', 'Education & Research'),
    ('iet davv', 'Education & Research'),
    ('kiet', 'Education & Research'),
    ('banasthali', 'Education & Research'),
    ('pes uni', 'Education & Research'),
    # Healthcare
    ('hospital', 'Healthcare & Life Sciences'),
    ('pharma', 'Healthcare & Life Sciences'),
    ('biotech', 'Healthcare & Life Sciences'),
    ('medical', 'Healthcare & Life Sciences'),
    ('healthcare', 'Healthcare & Life Sciences'),
    ('health care', 'Healthcare & Life Sciences'),
    # Government
    ('government', 'Government & Public Sector'),
    ('ministry', 'Government & Public Sector'),
    ('defence', 'Government & Public Sector'),
    ('defense', 'Government & Public Sector'),
    ('drdo', 'Government & Public Sector'),
    ('isro', 'Government & Public Sector'),
    # Telecom
    ('airtel', 'Telecom'),
    ('jio', 'Telecom'),
    ('vodafone', 'Telecom'),
    ('telecom', 'Telecom'),
    # Manufacturing
    ('motors', 'Manufacturing & Engineering'),
    ('steel', 'Manufacturing & Engineering'),
    ('energy', 'Manufacturing & Engineering'),
    ('power', 'Manufacturing & Engineering'),
    ('tata motors', 'Manufacturing & Engineering'),
    ('mahindra', 'Manufacturing & Engineering'),
    ('larsen', 'Manufacturing & Engineering'),
    ('l&t', 'Manufacturing & Engineering'),
    # Media
    ('media', 'Media & Design'),
    ('entertainment', 'Media & Design'),
    ('studio', 'Media & Design'),
    # Tech keywords in org names
    ('software', 'Technology'),
    ('technologies', 'Technology'),
    ('tech ', 'Technology'),
    ('infotech', 'Technology'),
    ('solutions', 'Technology'),
    ('systems', 'Technology'),
    ('digital', 'Technology'),
    ('consulting', 'Business & Commerce'),
    ('consultancy', 'Business & Commerce'),
    ('bank', 'Business & Commerce'),
    ('financial', 'Business & Commerce'),
    ('insurance', 'Business & Commerce'),
    ('capital', 'Business & Commerce'),
    ('securities', 'Business & Commerce'),
]


def _infer_from_organization(org):
    """Try to infer industry from organization name (last resort for 'Other')."""
    if not org:
        return ''
    cleaned = org.strip().strip('"').strip()
    low = cleaned.lower()
    if not low or low in ('na', 'n/a', 'none', 'other', 'others', '-', 'student'):
        return ''
    if low in _TECH_ORGS:
        return 'Technology'
    if low in _BIZ_ORGS:
        return 'Business & Commerce'
    # Partial match: check if any known org name is a prefix of the input
    for name in _TECH_ORGS:
        if low.startswith(name + ' ') or low.startswith(name + ','):
            return 'Technology'
    for name in _BIZ_ORGS:
        if low.startswith(name + ' ') or low.startswith(name + ','):
            return 'Business & Commerce'
    for keyword, industry in _ORG_KEYWORDS:
        if keyword in low:
            return industry
    return ''


_PERSONA_INDUSTRY_FALLBACK = {
    'Backend Developer': 'Technology',
    'Frontend Developer': 'Technology',
    'Full Stack Developer': 'Technology',
    'Mobile Developer': 'Technology',
    'Web Developer': 'Technology',
    'Software Developer': 'Technology',
    'DevOps / Cloud Engineer': 'Technology',
    'Cyber Security': 'Technology',
    'Architect': 'Technology',
    'QA / Testing': 'Technology',
    'Embedded / IoT': 'Technology',
    'Game Developer': 'Technology',
    'AI / ML Engineer': 'Data & AI',
    'Data Analyst / Data Engineer': 'Data & AI',
    'UI/UX Designer': 'Media & Design',
    'Product / Manager': 'Business & Commerce',
    'Sales / Marketing': 'Business & Commerce',
    'Finance / Accounts': 'Business & Commerce',
    'HR / Operations': 'Business & Commerce',
    'Academic / Research': 'Education & Research',
    'Student / Fresher': 'Education & Research',
}


def get_industry(domain, designation=None, organization=None, persona=None):
    """Map a raw domain string to its industry category.
    Falls back to keyword inference from designation if domain is
    unmapped or blank, then to organization name, then to persona.
    Returns '' only if nothing can be inferred."""
    if domain and isinstance(domain, str) and domain.strip():
        mapped = _DOMAIN_INDUSTRY_LOOKUP.get(domain.strip().lower())
        if mapped:
            return mapped
        inferred = _infer_from_designation(designation) if designation else ''
        if inferred:
            return inferred
        if organization:
            org_inferred = _infer_from_organization(organization)
            if org_inferred:
                return org_inferred
        return domain.strip()

    if designation:
        inferred = _infer_from_designation(designation)
        if inferred:
            return inferred

    if organization:
        org_inferred = _infer_from_organization(organization)
        if org_inferred:
            return org_inferred

    if persona and persona in _PERSONA_INDUSTRY_FALLBACK:
        return _PERSONA_INDUSTRY_FALLBACK[persona]

    return ''


# Storage key "Technology" is shown as "Information Technology" on the dashboard chart.
_INDUSTRY_DISPLAY_LABELS = {
    'Technology': 'Information Technology',
}


def canonical_industry(raw) -> str:
    """Map a stored industry or domain string to an INDUSTRY_DOMAIN_MAP key.

    Domain-level values such as "Software development" roll up to "Technology".
    Returns '' for empty, Other, or anything that cannot be classified.
    """
    if not raw or not isinstance(raw, str):
        return ''
    name = raw.strip()
    if not name or name.lower() == 'other':
        return ''
    if name == 'Information Technology':
        return 'Technology'
    if name in INDUSTRY_DOMAIN_MAP:
        return name
    mapped = _DOMAIN_INDUSTRY_LOOKUP.get(name.lower())
    if not mapped or mapped.lower() == 'other':
        return ''
    return mapped


def industry_chart_label(canonical: str) -> str:
    """Dashboard label for a canonical industry key."""
    if not canonical:
        return ''
    return _INDUSTRY_DISPLAY_LABELS.get(canonical, canonical)


def accumulate_industry_buckets(
    buckets: dict,
    raw_industry=None,
    domain=None,
    n=0,
    designation=None,
    organization=None,
    persona=None,
) -> None:
    """Add *n* users into *buckets* keyed by canonical industry.

    Stored industry is used when it is already a known category; otherwise the
    domain (and designation/org/persona fallbacks) are mapped the same way as
    ``get_industry``. Domain names are kept under each industry for drill-down.
    """
    n = int(n or 0)
    if n <= 0:
        return
    key = canonical_industry(raw_industry)
    if not key:
        key = canonical_industry(domain)
    if not key:
        inferred = get_industry(domain, designation, organization, persona)
        key = canonical_industry(inferred)
    if not key:
        return
    bucket = buckets.setdefault(key, {'total': 0, 'domains': defaultdict(int)})
    bucket['total'] += n
    dlabel = domain.strip() if isinstance(domain, str) else ''
    if dlabel and dlabel.lower() != 'other':
        bucket['domains'][dlabel] += n


def industry_buckets_to_chart(buckets: dict) -> list:
    """Convert accumulate_industry_buckets output into dashboard chart series."""
    out = []
    for key, bucket in (buckets or {}).items():
        domains = [
            {'label': lbl, 'value': int(val)}
            for lbl, val in (bucket.get('domains') or {}).items()
        ]
        domains.sort(key=lambda x: -x['value'])
        out.append({
            'label': industry_chart_label(key),
            'value': int(bucket.get('total') or 0),
            'domains': domains,
        })
    out.sort(key=lambda x: -x['value'])
    return out
