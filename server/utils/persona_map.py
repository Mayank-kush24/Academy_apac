"""
Designation -> Persona mapping.

Cleans messy, user-filled designation strings and maps them to one of 14
broader persona categories using keyword matching + fuzzy matching (rapidfuzz).

Usage:
    from server.utils.persona_map import get_persona
    persona = get_persona("Sr Backend Dev (5 yrs)", occupation="professional")
    # => "Backend Developer"
"""

import re
from rapidfuzz import process, fuzz

# ---------------------------------------------------------------------------
# Easily extendable keyword -> persona mapping.
# Order within each list: more specific phrases first.
# ---------------------------------------------------------------------------

PERSONA_KEYWORDS = {

    # ------------------------------------------------
    # CORE SOFTWARE ROLES
    # ------------------------------------------------
    'Backend Developer': [
        'backend developer','backend engineer','backend dev',
        'back end developer','back-end developer',
        'server side developer','api developer',
        'java developer','spring boot developer',
        'node developer','nodejs developer',
        'django developer','flask developer',
        '.net developer','.net engineer',
        'php developer','golang developer'
    ],

    'Frontend Developer': [
        'frontend developer','frontend engineer','frontend dev',
        'front end developer','front-end developer',
        'ui developer','ui engineer',
        'react developer','angular developer',
        'vue developer','javascript developer',
        'typescript developer'
    ],

    'Full Stack Developer': [
        'full stack developer','fullstack developer',
        'full-stack developer','full stack engineer',
        'mern stack','mean stack',
        'software developer full stack'
    ],

    'Mobile Developer': [
        'mobile developer','mobile app developer',
        'mobile application developer',
        'android developer','android engineer',
        'ios developer','ios engineer',
        'flutter developer','react native developer',
        'swift developer','kotlin developer'
    ],

    'Web Developer': [
        'web developer','web dev','web engineer',
        'website developer','web application developer'
    ],

    'Software Developer': [
        'software engineer','software developer',
        'software dev','software engg',
        'application developer','application engineer',
        'sde','swe',
        'programmer','coder',
        'developer','engineer'
    ],

    # ------------------------------------------------
    # AI / ML
    # ------------------------------------------------
    'AI / ML Engineer': [
        'ai engineer','ai developer','ai dev',
        'ai/ml engineer','ai ml engineer',
        'machine learning engineer','ml engineer',
        'deep learning engineer',
        'nlp engineer','computer vision engineer',
        'generative ai','gen ai',
        'llm engineer','prompt engineer',
        'ai researcher','ai scientist'
    ],

    # ------------------------------------------------
    # DATA
    # ------------------------------------------------
    'Data Analyst / Data Engineer': [
        'data analyst','data engineer',
        'data scientist','data science',
        'analytics engineer','analytics analyst',
        'business intelligence','bi analyst',
        'bi developer','big data engineer',
        'data architect','data consultant'
    ],

    # ------------------------------------------------
    # DEVOPS / CLOUD
    # ------------------------------------------------
    'DevOps / Cloud Engineer': [
        'devops engineer','devops','devops engg',
        'cloud engineer','cloud architect',
        'cloud developer',
        'site reliability engineer','sre',
        'platform engineer',
        'infrastructure engineer',
        'kubernetes engineer',
        'docker engineer',
        'aws engineer','azure engineer','gcp engineer'
    ],

    # ------------------------------------------------
    # SECURITY
    # ------------------------------------------------
    'Cyber Security': [
        'cybersecurity analyst','cybersecurity engineer',
        'cybersecurity researcher',
        'cyber security analyst','cyber security engineer',
        'security analyst','security engineer',
        'information security','infosec',
        'penetration tester','ethical hacker',
        'security consultant'
    ],

    # ------------------------------------------------
    # ARCHITECTS
    # ------------------------------------------------
    'Architect': [
        'software architect','solution architect',
        'solutions architect','system architect',
        'enterprise architect','technical architect',
        'cloud architect','ai architect'
    ],

    # ------------------------------------------------
    # QA / TESTING
    # ------------------------------------------------
    'QA / Testing': [
        'qa engineer','qa analyst',
        'quality assurance','test engineer',
        'software tester','automation tester',
        'test automation engineer',
        'manual tester'
    ],

    # ------------------------------------------------
    # EMBEDDED / IOT
    # ------------------------------------------------
    'Embedded / IoT': [
        'embedded engineer','embedded developer',
        'firmware engineer','firmware developer',
        'iot engineer','robotics engineer',
        'electronics engineer'
    ],

    # ------------------------------------------------
    # GAME DEV
    # ------------------------------------------------
    'Game Developer': [
        'game developer','unity developer',
        'unreal developer','game engineer'
    ],

    # ------------------------------------------------
    # DESIGN
    # ------------------------------------------------
    'UI/UX Designer': [
        'ui designer','ux designer','ui ux designer',
        'product designer','interaction designer',
        'graphic designer','visual designer'
    ],

    # ------------------------------------------------
    # PRODUCT / MANAGEMENT
    # ------------------------------------------------
    'Product / Manager': [
        'product manager','product owner',
        'project manager','program manager',
        'engineering manager',
        'tech lead','technical lead',
        'scrum master','agile coach',
        'team lead','team leader'
    ],

    # ------------------------------------------------
    # SALES / MARKETING
    # ------------------------------------------------
    'Sales / Marketing': [
        'marketing manager','digital marketing',
        'growth marketer','seo specialist',
        'sales manager','business development',
        'bdm','account manager',
        'account executive'
    ],

    # ------------------------------------------------
    # FINANCE
    # ------------------------------------------------
    'Finance / Accounts': [
        'accountant','accounts executive',
        'accounts manager','finance analyst',
        'finance manager','bookkeeper'
    ],

    # ------------------------------------------------
    # HR / OPERATIONS
    # ------------------------------------------------
    'HR / Operations': [
        'hr manager','human resources',
        'recruiter','talent acquisition',
        'operations manager','operations executive',
        'admin','administrator'
    ],

    # ------------------------------------------------
    # ACADEMIC / RESEARCH
    # ------------------------------------------------
    'Academic / Research': [
        'researcher','research scientist',
        'faculty','professor','lecturer',
        'academic associate','academic coordinator',
        'academic counselor'
    ],

    # ------------------------------------------------
    # STUDENT
    # ------------------------------------------------
    'Student / Fresher': [
        'student','intern','fresher',
        'graduate','undergraduate',
        'trainee','graduate trainee'
    ]
}

# ---------------------------------------------------------------------------
# Pre-built flat list for fuzzy matching: [(keyword, persona), ...]
# Built once at import time for performance.
# ---------------------------------------------------------------------------

_FUZZY_CHOICES = []
_FUZZY_CHOICE_TO_PERSONA = {}

for _persona, _keywords in PERSONA_KEYWORDS.items():
    for _kw in _keywords:
        _FUZZY_CHOICES.append(_kw)
        _FUZZY_CHOICE_TO_PERSONA[_kw] = _persona

# Pre-built ordered list for keyword matching.
# More specific personas (multi-word keywords) are checked before generic ones
# like "Software Developer" whose keywords ("developer", "engineer") would
# otherwise shadow everything.
_KEYWORD_MATCH_ORDER = [
    'Backend Developer',
    'Frontend Developer',
    'Full Stack Developer',
    'Mobile Developer',
    'Web Developer',
    'AI / ML Engineer',
    'Data Analyst / Data Engineer',
    'DevOps / Cloud Engineer',
    'Cyber Security',
    'Architect',
    'QA / Testing',
    'Embedded / IoT',
    'Game Developer',
    'UI/UX Designer',
    'Product / Manager',
    'Sales / Marketing',
    'Finance / Accounts',
    'HR / Operations',
    'Academic / Research',
    'Student / Fresher',
    'Software Developer',  # generic catch-all last
]


def _extract_designation(raw):
    """Remove parenthesized text (experience info) from raw designation."""
    if not raw:
        return ''
    return re.sub(r'\([^)]*\)', '', raw).strip()


def _normalize(text):
    """Lowercase, strip whitespace, collapse spaces, remove non-alphanumeric
    chars except spaces, slashes and hyphens."""
    if not text:
        return ''
    t = text.lower().strip()
    t = re.sub(r'[^a-z0-9\s/\-]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _keyword_match(cleaned):
    """Return persona if any keyword is found in the cleaned designation."""
    if not cleaned:
        return None
    for persona in _KEYWORD_MATCH_ORDER:
        keywords = PERSONA_KEYWORDS[persona]
        for kw in keywords:
            if kw in cleaned:
                return persona
    return None


def _fuzzy_match(cleaned, score_cutoff=80):
    """Return persona using rapidfuzz fuzzy matching against all known keywords."""
    if not cleaned or len(cleaned) < 2:
        return None
    result = process.extractOne(
        cleaned,
        _FUZZY_CHOICES,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=score_cutoff,
    )
    if result:
        matched_keyword = result[0]
        return _FUZZY_CHOICE_TO_PERSONA.get(matched_keyword)
    return None


def get_persona(designation, occupation=None):
    """Map a raw designation string to a persona category.

    Pipeline:
      1. Extract designation (strip brackets/experience)
      2. Normalize (lowercase, trim, strip punctuation)
      3. Keyword match
      4. Fuzzy match (rapidfuzz, threshold 80)
      5. Fallback: check occupation for student/intern

    Returns one of the PERSONA_KEYWORDS keys, or 'Other'.
    """
    extracted = _extract_designation(designation)
    cleaned = _normalize(extracted)

    if not cleaned:
        if occupation and _is_student_occupation(occupation):
            return 'Student / Fresher'
        return 'Other'

    persona = _keyword_match(cleaned)
    if persona:
        return persona

    persona = _fuzzy_match(cleaned)
    if persona:
        return persona

    if occupation and _is_student_occupation(occupation):
        return 'Student / Fresher'

    return 'Other'


def _is_student_occupation(occupation):
    """Check if the occupation string indicates a student or intern."""
    if not occupation:
        return False
    occ = occupation.lower().strip()
    return any(kw in occ for kw in ('student', 'intern', 'fresher'))
