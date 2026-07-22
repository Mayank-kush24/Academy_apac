"""Unit tests for server.utils.badge_verify (mocked HTTP)."""
from datetime import date
from unittest.mock import patch

from server.utils.badge_verify import clean_expected_course, verify_badge


def test_cohort2_student_problem_statement_maps_to_badge_title():
    raw = "[Student] Track - Building AI Agents with ADK : From Single Agents to Multi-Agent Systems,"
    assert clean_expected_course(raw) == "Engineer AI Agents with Agent Development Kit (ADK)"


def test_cohort2_professional_track1_maps_to_badge_title():
    raw = "[Professional] Track 1 - Conversational Analytics with BigQuery Agents,"
    assert clean_expected_course(raw) == "Build AI Agents with Enterprise Databases"


def test_cohort2_professional_track2_maps_to_badge_title():
    raw = "[Professional] Track 2 - AI-Assisted Data Science with BigQuery,"
    assert clean_expected_course(raw) == "Agent Assist and its Gen AI Capabilities"


def test_clean_expected_course_legacy_when_badge_name_in_problem_statement():
    raw = "[Professional] Track 2 - Agent Assist and its Gen AI Capabilities,"
    assert clean_expected_course(raw) == "Agent Assist and its Gen AI Capabilities"


def test_clean_expected_course_strips_student_track_prefix_legacy():
    raw = "[Student] Track 3 - Engineer AI Agents with Agent Development Kit (ADK),"
    assert clean_expected_course(raw) == "Engineer AI Agents with Agent Development Kit (ADK)"


def test_clean_expected_course_strips_leading_asterisk():
    raw = "* [Professional] Track 2 - AI-Assisted Data Science with BigQuery,"
    assert clean_expected_course(raw) == "Agent Assist and its Gen AI Capabilities"


GOOGLE_URL = "https://www.cloudskillsboost.google/public_profiles/abc-123/badges/999999"
CREDLY_URL = "https://www.credly.com/badges/test-badge-id/public_url"


def test_google_valid_url_matching_title_and_date():
    html = """
    <html><head><title>Page</title></head><body>
    <h1 class="badge-title">Agent Assist and its Gen AI Capabilities</h1>
    <span class="completed-at">2026-04-12</span>
    </body></html>
    """
    with patch("server.utils.badge_verify.make_request", return_value=(200, html, GOOGLE_URL)):
        r = verify_badge(
            GOOGLE_URL,
            "[Professional] Track 2 - AI-Assisted Data Science with BigQuery,",
        )
    assert r["status"] == "verified"
    assert r["valid"] is True
    assert r["platform"] == "google"
    assert r["completion_date"] == "2026-04-12"


def test_google_invalid_path():
    url = "https://www.cloudskillsboost.google/badges/123"
    r = verify_badge(url, "Any Course")
    assert r["status"] == "failed"
    assert "Incorrect Path" in r["remarks"]


def test_google_wrong_host():
    r = verify_badge("https://example.com/public_profiles/x/badges/1", "Course")
    assert r["status"] == "failed"
    assert "Unsupported badge host" in r["remarks"] or "Incorrect Domain" in r["remarks"]


def test_google_title_mismatch():
    html = """
    <html><body>
    <h1 class="badge-title">Completely Different Course Title</h1>
    <span class="completed-at">2026-04-12</span>
    </body></html>
    """
    with patch("server.utils.badge_verify.make_request", return_value=(200, html, GOOGLE_URL)):
        r = verify_badge(
            GOOGLE_URL,
            "Agent Assist and its Gen AI Capabilities",
        )
    assert r["status"] == "failed"
    assert "Course mismatch" in r["remarks"]


def test_credly_valid_url_matching_meta_title_and_date():
    html = """
    <html><head>
    <meta property="og:title" content="My Credly Badge Name" />
    <script type="application/ld+json">
    {"@type":"CreativeWork","dateIssued":"2026-02-15"}
    </script>
    </head><body></body></html>
    """
    with patch("server.utils.badge_verify.make_request", return_value=(200, html, CREDLY_URL)):
        r = verify_badge(CREDLY_URL, "My Credly Badge Name")
    assert r["status"] == "verified"
    assert r["valid"] is True
    assert r["platform"] == "credly"
    assert r["completion_date"] == "2026-02-15"


def test_credly_completion_before_min_date():
    html = """
    <html><head>
    <meta property="og:title" content="Same Badge" />
    <script type="application/ld+json">{"dateIssued":"2026-03-01"}</script>
    </head><body></body></html>
    """
    with patch("server.utils.badge_verify.make_request", return_value=(200, html, CREDLY_URL)):
        r = verify_badge(
            CREDLY_URL,
            "Same Badge",
            min_date=date(2026, 5, 1),
        )
    assert r["status"] == "failed"
    assert "before cutoff" in r["remarks"]


def test_pending_when_request_fails():
    import requests

    with patch(
        "server.utils.badge_verify.make_request",
        side_effect=requests.RequestException("timeout"),
    ):
        r = verify_badge(GOOGLE_URL, "Agent Assist and its Gen AI Capabilities")
    assert r["status"] == "pending"
    assert r["valid"] is False
    assert "Pending:" in r["remarks"]


def test_min_date_none_accepts_old_completion_date():
    html = """
    <html><body>
    <h1 class="badge-title">Agent Assist and its Gen AI Capabilities</h1>
    <span class="completed-at">2020-01-01</span>
    </body></html>
    """
    with patch("server.utils.badge_verify.make_request", return_value=(200, html, GOOGLE_URL)):
        r = verify_badge(
            GOOGLE_URL,
            "Agent Assist and its Gen AI Capabilities",
            min_date=None,
        )
    assert r["status"] == "verified"
    assert r["completion_date"] == "2020-01-01"
