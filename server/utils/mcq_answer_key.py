"""
Hardcoded correct answers for Optional MCQ tracks (1, 2, 3).
Used to validate participant responses by track_number and question_id.
"""

from typing import Optional

# Valid question IDs and options for validation (internal key format: Q1..Q10)
VALID_QUESTION_IDS = frozenset(f"Q{i}" for i in range(1, 11))
VALID_OPTIONS = frozenset("ABCD")
VALID_TRACKS = frozenset({1, 2, 3})

# Map DB column names (question_1..question_10) and Q1..Q10 to canonical Q1..Q10 (keys lowercase for lookup)
QUESTION_ID_ALIASES = {}
for i in range(1, 11):
    QUESTION_ID_ALIASES[f"question_{i}"] = f"Q{i}"
    QUESTION_ID_ALIASES[f"q{i}"] = f"Q{i}"


def _normalize_question_id(question_id: Optional[str]) -> Optional[str]:
    """Accept 'Q1'..'Q10' or 'question_1'..'question_10' (case-insensitive). Return 'Q1'..'Q10' or None."""
    if not question_id or not str(question_id).strip():
        return None
    key = str(question_id).strip().lower()
    return QUESTION_ID_ALIASES.get(key) or (key.upper() if key.upper() in VALID_QUESTION_IDS else None)

# Track-wise question text for display (e.g. in View submission modal)
TRACK_QUESTIONS = {
    1: [
        "Q1. What best defines an \"agentic AI\" system?",
        "Q2. Why does this workshop emphasize moving beyond notebooks and prototypes?",
        "Q3. What role does the Agent Development Kit (ADK) play in building agentic applications?",
        "Q4. In agentic application design, why is defining clear agent responsibilities important?",
        "Q5. In the hands-on lab, what is the primary function of the Zoo Agent?",
        "Q6. Why are AI agents packaged as containerized services before deployment?",
        "Q7. Which Cloud Run feature makes it well-suited for AI agent workloads?",
        "Q8. After deployment to Cloud Run, how is the AI agent typically accessed by users or other services?",
        "Q9. What is the primary purpose of using IAM for service-to-service communication in this workshop?",
        "Q10. Why does the lab include steps to delete Cloud resources after completion?",
    ],
    2: [
        "Q1. What is the primary purpose of Model Context Protocol (MCP) in agentic AI systems?",
        "Q2. Which architectural principle is demonstrated by separating the agent (reasoning layer) from the MCP server (tooling layer)?",
        "Q3. What role does an MCP Server play in this workshop architecture?",
        "Q4. How do AI agents discover and invoke tools when using MCP?",
        "Q5. In the hands-on lab, what is the primary role of the Zoo Tour Guide Agent?",
        "Q6. Why is business logic kept out of the AI model when using MCP-based designs?",
        "Q7. Why is Cloud Run used to deploy both the MCP server and the AI agent?",
        "Q8. What is the purpose of using IAM when an AI agent connects to a remote MCP server?",
        "Q9. Which scenario best illustrates the benefit of MCP in production AI systems?",
        "Q10. Why does the lab include steps to delete Cloud resources after completion?",
    ],
    3: [
        "Q1. What is the primary focus of AlloyDB for PostgreSQL in AI-powered applications?",
        "Q2. Why does this workshop emphasize using managed databases when building AI-powered applications?",
        "Q3. Which familiar managed database option is discussed alongside AlloyDB in this workshop?",
        "Q4. What capability allows AlloyDB to convert user intent into executable database queries?",
        "Q5. What is the first step required to start using AI natural language features in AlloyDB?",
        "Q6. In the hands-on lab, how are SQL queries generated for AlloyDB?",
        "Q7. Why is tuning configuration important when using AI-assisted natural language queries in AlloyDB?",
        "Q8. What is a key advantage of using AlloyDB AI features without adding additional AI infrastructure?",
        "Q9. Which outcome best represents how AlloyDB directly powers AI features in applications?",
        "Q10. Why does the lab include steps to deploy AlloyDB using Google Cloud Console and Cloud Shell?",
    ],
}

ANSWER_KEY = {
    1: {
        "Q1": "C",
        "Q2": "C",
        "Q3": "C",
        "Q4": "B",
        "Q5": "C",
        "Q6": "C",
        "Q7": "C",
        "Q8": "C",
        "Q9": "B",
        "Q10": "B",
    },
    2: {
        "Q1": "B",
        "Q2": "C",
        "Q3": "C",
        "Q4": "C",
        "Q5": "C",
        "Q6": "C",
        "Q7": "C",
        "Q8": "B",
        "Q9": "C",
        "Q10": "B",
    },
    3: {
        "Q1": "B",
        "Q2": "C",
        "Q3": "C",
        "Q4": "C",
        "Q5": "B",
        "Q6": "C",
        "Q7": "B",
        "Q8": "C",
        "Q9": "C",
        "Q10": "B",
    },
}


def validate_answer(
    track_number: int,
    question_id: str,
    selected_option: Optional[str],
) -> dict:
    """
    Validate a single MCQ answer against the hardcoded answer key.

    Args:
        track_number: 1, 2, or 3.
        question_id: "Q1".."Q10" or DB column name "question_1".."question_10" (case-insensitive).
        selected_option: "A", "B", "C", or "D" (case-insensitive).

    Returns:
        {
            "is_correct": True | False,
            "correct_answer": "C" | None,  # None if track/question invalid
            "error": str | None,             # Set for invalid inputs
        }
    """
    result = {"is_correct": False, "correct_answer": None, "error": None}

    if track_number not in VALID_TRACKS:
        result["error"] = f"Invalid track_number: {track_number}. Must be 1, 2, or 3."
        return result

    qid = _normalize_question_id(question_id)
    if not qid or qid not in VALID_QUESTION_IDS:
        result["error"] = f"Invalid question_id: {question_id}. Use Q1..Q10 or question_1..question_10."
        return result

    if selected_option is None or (isinstance(selected_option, str) and not selected_option.strip()):
        result["correct_answer"] = ANSWER_KEY[track_number][qid]
        result["error"] = "Missing selected_option."
        return result

    option = str(selected_option).strip().upper()
    if len(option) >= 1:
        option = option[0]
    if option not in VALID_OPTIONS:
        result["correct_answer"] = ANSWER_KEY[track_number][qid]
        result["error"] = f"Invalid selected_option: {selected_option}. Must be A, B, C, or D."
        return result

    correct = ANSWER_KEY[track_number][qid]
    result["correct_answer"] = correct
    result["is_correct"] = option == correct
    result["error"] = None
    return result


def get_track_questions(track_number: int) -> list:
    """Return list of 10 question strings for the track (for display in View submission)."""
    if track_number not in VALID_TRACKS:
        return [f"Q{i}." for i in range(1, 11)]
    return list(TRACK_QUESTIONS.get(track_number, [f"Q{i}." for i in range(1, 11)]))


def get_correct_answer(track_number: int, question_id: str) -> Optional[str]:
    """
    Return the correct answer for a track/question, or None if invalid.
    question_id can be "Q1".."Q10" or "question_1".."question_10".
    """
    if track_number not in VALID_TRACKS:
        return None
    qid = _normalize_question_id(question_id)
    if not qid or qid not in VALID_QUESTION_IDS:
        return None
    return ANSWER_KEY[track_number].get(qid)


def extract_option_from_response(response: Optional[str]) -> Optional[str]:
    """
    Extract option letter (A/B/C/D) from stored response text.
    Handles "C", "C. An AI system", "c. Something", etc. Returns None if not recognizable.
    """
    if response is None or not str(response).strip():
        return None
    first = str(response).strip().upper()[0:1]
    return first if first in VALID_OPTIONS else None


def score_submission(
    track_number: int,
    question_1: Optional[str] = None,
    question_2: Optional[str] = None,
    question_3: Optional[str] = None,
    question_4: Optional[str] = None,
    question_5: Optional[str] = None,
    question_6: Optional[str] = None,
    question_7: Optional[str] = None,
    question_8: Optional[str] = None,
    question_9: Optional[str] = None,
    question_10: Optional[str] = None,
) -> dict:
    """
    Auto-score one MCQ submission against the answer key.
    Returns dict: correct_count, score_display ("8/10"), results (list of per-question validation).
    """
    responses = [
        question_1, question_2, question_3, question_4, question_5,
        question_6, question_7, question_8, question_9, question_10,
    ]
    results = []
    correct_count = 0
    for i in range(1, 11):
        raw = responses[i - 1]
        selected = extract_option_from_response(raw)
        v = validate_answer(track_number, f"Q{i}", selected)
        results.append({
            "question_id": f"Q{i}",
            "raw": str(raw).strip() if raw else "",
            "selected_option": selected,
            "correct_answer": v.get("correct_answer"),
            "is_correct": v.get("is_correct", False),
        })
        if v.get("is_correct"):
            correct_count += 1
    return {
        "correct_count": correct_count,
        "score_display": f"{correct_count}/10",
        "results": results,
    }
