"""
Main MCQ (MCQ Verification) — text-based correct answers for tracks 1, 2, 3.
Used to validate participant free-text responses by normalizing and comparing
to the correct answer text (with optional fuzzy matching).
"""

import re
from typing import Optional, List

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

VALID_TRACKS = frozenset({1, 2, 3})
SIMILARITY_THRESHOLD = 85  # Count as correct if ratio >= this (0-100)

TRACK_QUESTIONS = {
    1: [
        "In the lab, you created a tour_guide_workflow using a SequentialAgent that runs comprehensive_researcher first and response_formatter second. Why was a SequentialAgent used instead of a normal Agent?",
        "In the lab, the agent stores the user's prompt using tool_context.state['PROMPT'] = prompt. Since Cloud Run is stateless by default, what happens to this stored state if the service scales to zero and later receives a new request?",
        "You created a dedicated service account for the Cloud Run service and granted it the role roles/aiplatform.user. Why was this role necessary?",
        "During setup, you enabled the Artifact Registry API before deployment. Why was this required?",
        "In the architecture, the root_agent greets the user, saves the prompt, and passes control to tour_guide_workflow. What is its primary role?",
        "You wrapped WikipediaQueryRun inside LangchainTool(...) before using it in the ADK agent. Why was this necessary?",
        "The comprehensive_researcher agent used output_key='research_data'. What is the purpose of this parameter?",
        "You used load_dotenv() and retrieved values like MODEL from environment variables instead of hardcoding them. Why is this considered good cloud practice?",
        "Cloud Run is described as cost-efficient because it supports scaling to zero and request-based billing. Why is this especially useful for this lab's AI agent?",
        "You enabled the Compute Engine API even though you deployed to Cloud Run. Why might this still be required?",
    ],
    2: [
        "In the lab, you built a Zoo Tour Guide agent using Google's Agent Development Kit (ADK) and connected it to an MCP server hosted on Cloud Run. What is the main architectural reason for keeping the ADK agent separate from the MCP server?",
        "In the lab, the Zoo agent connects to a private MCP server deployed on Cloud Run. Why does the MCP tool generate an ID token using google.oauth2.id_token.fetch_id_token()?",
        "During setup, you granted the service account the role roles/run.invoker on the MCP server. What would happen if this permission were missing?",
        "In the workflow, you used a SequentialAgent that first runs the Researcher agent and then the Response Formatter agent. Why was this design chosen?",
        "The add_prompt_to_state tool saves the user's prompt inside tool_context.state. Why is this necessary in the multi-agent workflow?",
        "Cloud Run is described as 'stateless by default' in the lab. What does this imply for your Zoo agent?",
        "When deploying the agent, you used the --with_ui flag. What is the purpose of this flag?",
        "The service account was granted the roles/aiplatform.user role. Why is this required?",
        "If 1,000 users simultaneously access the deployed Zoo agent on Cloud Run, how does Cloud Run handle the traffic?",
        "The Researcher agent can use both the MCP tool (zoo database) and the Wikipedia tool. Why is it sometimes necessary to use both?",
    ],
    3: [
        "While creating private service access for AlloyDB, why is the --purpose=VPC_PEERING flag required when reserving the IP range?",
        "If the alloydb_ai_nl_enabled database flag is not turned on before creating the extension, what is the most likely outcome?",
        "Why is CREATE EXTENSION google_ml_integration; executed before alloydb_ai_nl?",
        "After generating schema context automatically, why did the query initially reference inventory_items instead of products?",
        "What is the purpose of adding general context like defining 'Clades' as a preferred brand?",
        "Why is alloydb_ai_nl.generate_schema_context() potentially time-consuming?",
        "What is the main advantage of creating a Value Index for brand_name?",
        "Why was a query template created for the 'Republic Outpost' use case?",
        "What is the role of roles/aiplatform.user in the IAM policy binding step?",
        "Why must a private IP range exist before creating the AlloyDB cluster?",
    ],
}

ANSWER_KEY = {
    1: [
        "To enforce a fixed order of execution without independent reasoning",
        "The state is lost because each request may run in a new container instance",
        "To allow the agent to call Gemini models through Vertex AI",
        "Because deployment builds and pushes a container image before running",
        "Orchestrating the first interaction and delegating control",
        "To convert a LangChain tool into an ADK-compatible tool interface",
        "To store the agent's output in shared workflow state",
        "It separates configuration from application logic",
        "You only pay when the service is actively handling requests",
        "Cloud Run depends on underlying compute infrastructure",
    ],
    2: [
        "To separate reasoning logic from tool/data access",
        "To authenticate securely with a private Cloud Run service",
        "The agent would deploy but fail when calling the MCP tool",
        "To enforce a structured, predictable execution order",
        "To allow later agents to access the original user prompt",
        "Each request may be handled by a different container instance",
        "Launches the ADK developer interface for testing",
        "To allow the service to call Vertex AI models",
        "Automatically creates additional container instances",
        "To combine internal zoo-specific data with general knowledge",
    ],
    3: [
        "To enable private connectivity between Google services and your VPC",
        "The extension installation fails",
        "It enables model endpoint connectivity required for NL features",
        "The generated context lacked business semantics",
        "To bias NL interpretation toward business assumptions",
        "It scans metadata and relationships across schema objects",
        "Better identification of value phrases in NL queries",
        "To enforce stable SQL patterns for business-critical queries",
        "Grants the AlloyDB service agent access to Vertex AI",
        "It is required for Private Service Access",
    ],
}


def _normalize_text(text: Optional[str]) -> str:
    """Lowercase, strip, collapse spaces, remove punctuation for comparison."""
    if not text or not str(text).strip():
        return ""
    t = str(text).strip().lower()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _is_correct_response(participant: Optional[str], correct: Optional[str]) -> bool:
    """Return True if participant response matches correct answer (exact after normalize, or fuzzy >= threshold)."""
    if correct is None or (isinstance(correct, str) and not correct.strip()):
        return False
    part_norm = _normalize_text(participant)
    correct_norm = _normalize_text(correct)
    if not correct_norm:
        return False
    if part_norm == correct_norm:
        return True
    if HAS_RAPIDFUZZ and part_norm:
        ratio = fuzz.token_sort_ratio(part_norm, correct_norm)
        return ratio >= SIMILARITY_THRESHOLD
    return False


def validate_answer(
    track_number: int,
    question_index_1_based: int,
    participant_response: Optional[str],
) -> dict:
    """
    Validate a single main MCQ answer (1-based question index 1..10).
    Returns { "is_correct": bool, "correct_answer": str or None }.
    """
    result = {"is_correct": False, "correct_answer": None}
    if track_number not in VALID_TRACKS or not (1 <= question_index_1_based <= 10):
        return result
    answers = ANSWER_KEY.get(track_number)
    if not answers or question_index_1_based > len(answers):
        return result
    correct = answers[question_index_1_based - 1]
    result["correct_answer"] = correct
    result["is_correct"] = _is_correct_response(participant_response, correct)
    return result


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
    Auto-score one Main MCQ submission against the answer key.
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
        v = validate_answer(track_number, i, raw)
        results.append({
            "question_id": f"Q{i}",
            "raw": str(raw).strip() if raw else "",
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


def get_track_questions(track_number: int) -> List[str]:
    """Return list of 10 question strings for the track (for display in View submission)."""
    if track_number not in VALID_TRACKS:
        return [f"Q{i}." for i in range(1, 11)]
    return list(TRACK_QUESTIONS.get(track_number, [f"Q{i}." for i in range(1, 11)]))


def get_response_score(response_obj) -> dict:
    """
    Return same dict as score_submission but use response_obj.score when stored in DB.
    Use when reading MainMcqResponse so stored score is used when present.
    """
    if getattr(response_obj, "score", None) is not None:
        c = int(response_obj.score)
        c = max(0, min(10, c))
        return {
            "correct_count": c,
            "score_display": f"{c}/10",
            "results": [],
        }
    return score_submission(
        getattr(response_obj, "track_number", 1),
        getattr(response_obj, "question_1", None),
        getattr(response_obj, "question_2", None),
        getattr(response_obj, "question_3", None),
        getattr(response_obj, "question_4", None),
        getattr(response_obj, "question_5", None),
        getattr(response_obj, "question_6", None),
        getattr(response_obj, "question_7", None),
        getattr(response_obj, "question_8", None),
        getattr(response_obj, "question_9", None),
        getattr(response_obj, "question_10", None),
    )
