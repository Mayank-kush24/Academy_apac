"""Tests for raw company -> BOB company mapping."""
import os
from pathlib import Path

import pytest

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "bob_companies_sample.csv"
INDEX_PATH = Path(__file__).resolve().parent / "_company_index_test.pkl.gz"


@pytest.fixture(scope="module", autouse=True)
def company_index(tmp_path_factory):
    from scripts.build_company_index import build_index
    from server.utils import company_map

    out = tmp_path_factory.mktemp("company_index") / "company_index.pkl.gz"
    build_index(str(FIXTURE_CSV), str(out), str(out.with_suffix(".dupes.csv")), cohort_id=2)
    os.environ["COMPANY_INDEX_PATH"] = str(out)
    company_map.clear_index_cache()
    yield
    company_map.clear_index_cache()
    os.environ.pop("COMPANY_INDEX_PATH", None)


def test_exact_match():
    from server.utils.company_map import map_company

    assert map_company("Tata Consultancy Services") == "Tata Consultancy Services"


def test_fuzzy_match_strips_suffix():
    from server.utils.company_map import map_company

    assert map_company("Infosys Ltd") == "Infosys Limited"


def test_fuzzy_match_abbreviation():
    from server.utils.company_map import map_company

    matched = map_company("Amazon Web Services India")
    assert matched == "Amazon Web Services"


def test_no_match_returns_original():
    from server.utils.company_map import map_company

    raw = "Totally Unknown Startup XYZ"
    assert map_company(raw) == raw


def test_blank_returns_blank():
    from server.utils.company_map import map_company

    assert map_company("") == ""
    assert map_company("   ") == "   "


def test_get_bob_company_none_when_unmatched():
    from server.utils.company_map import get_bob_company

    assert get_bob_company("Unknown Corp") is None


def test_get_bob_company_returns_match():
    from server.utils.company_map import get_bob_company

    assert get_bob_company("Microsoft Corp") == "Microsoft Corporation"
