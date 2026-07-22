"""Tests for company name cleaning."""
from server.utils.company_name_clean import clean_company_name


def test_strip_wrapping_quotes():
    assert clean_company_name('""Adarsha Vidya Kendra College""') == "Adarsha Vidya Kendra College"
    assert clean_company_name('"HCLTECH"') == "HCLTECH"
    assert clean_company_name('""India Paper Products"') == "India Paper Products"


def test_strip_leading_dash_and_quotes():
    assert clean_company_name('- "Pursuing Software Engineering (Self-Study)') == (
        "Pursuing Software Engineering (Self-Study)"
    )


def test_mojibake_smart_quotes():
    raw = '"\u00e2\u20ac\u0153N/A \u00e2\u20ac\u201c Currently in Class 12 (School Student)'
    assert clean_company_name(raw) == ""


def test_junk_to_empty():
    assert clean_company_name("-") == ""
    assert clean_company_name("-----") == ""
    assert clean_company_name("6") == ""
    assert clean_company_name("2025") == ""
    assert clean_company_name('""') == ""
    assert clean_company_name("NA") == ""
    assert clean_company_name("  ") == ""
    assert clean_company_name("??????") == ""
    assert clean_company_name("???????????") == ""


def test_strip_question_mark_prefix():
    assert clean_company_name("?????? Bespin Global") == "Bespin Global"
    assert clean_company_name("???????????ESTsecurity") == "ESTsecurity"
    assert clean_company_name("????Sun Asterisk (Sun*)") == "Sun Asterisk (Sun*)"
    assert clean_company_name("Chainstack ?????") == "Chainstack"


def test_ftfy_double_encoding():
    raw = "\u00c3\u00a8\u00e2\u20ac\u00a2\u00e2\u20ac\u00b0\u00c3\u00a6\u00e2\u20ac\u0161\u00c2\u00a8\u00c3\u00a4\u00c2\u00be\u00e2\u20ac\u00a0\u00c3\u00a5\u00c2\u00a5\u00c2\u00bd\u00c3\u00a5\u00c2\u00ba\u00b7"
    assert clean_company_name(raw) == "蕉您來好康"


def test_strip_at_prefix():
    assert clean_company_name("@BelieversVision") == "BelieversVision"


def test_preserves_valid_names():
    assert clean_company_name("Tata Consultancy Services") == "Tata Consultancy Services"
    assert clean_company_name("ACCENTURE INDIA PRIVATE LIMITED") == "ACCENTURE INDIA PRIVATE LIMITED"
    assert clean_company_name("!Coconut") == "!Coconut"
