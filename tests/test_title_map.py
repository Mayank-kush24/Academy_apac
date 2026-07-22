"""Tests for designation -> title category mapping (client reference index)."""
from server.utils.title_map import BROAD_CATEGORIES, get_title_categories, map_title


def test_product_manager_exact_match():
    sub, broad = get_title_categories("Product Manager")
    assert sub == "Product Manager"
    assert broad == "Product End User"


def test_software_engineer_exact_match():
    sub, broad = get_title_categories("software engineer")
    assert sub == "Software Engineer"
    assert broad == "Technology End User"


def test_sde_fuzzy_match():
    sub, broad = get_title_categories("SDE-2")
    assert broad == "Technology End User"
    assert sub is not None


def test_student_excluded():
    sub, broad = get_title_categories("Computer Science Student")
    assert sub is None
    assert broad is None


def test_blank_designation_returns_none():
    assert get_title_categories("") == (None, None)
    assert get_title_categories("   ") == (None, None)
    assert get_title_categories("--") == (None, None)
    assert get_title_categories("Mr") == (None, None)


def test_bare_degree_returns_none():
    assert get_title_categories("B.Tech CSE") == (None, None)


def test_owner_with_form_suffix():
    sub, broad = get_title_categories("Owner( 5 )")
    assert sub is not None
    assert broad in BROAD_CATEGORIES


def test_president_maps_to_broad_category():
    sub, broad = get_title_categories("President")
    assert sub is not None
    assert broad in BROAD_CATEGORIES


def test_decimal_form_suffix_stripped():
    sub, broad = get_title_categories("Analyst( 2.5 )")
    assert sub == "Analyst"
    assert broad == "Data End User"


def test_below_threshold_returns_none():
    assert get_title_categories("Chief Llama Wrangler") == (None, None)
    assert map_title("Chief Llama Wrangler") == ("Unclassified", "Unclassified")


def test_supervisor_maps_to_broad_category():
    sub, broad = get_title_categories("Supervisor")
    assert sub is not None
    assert broad in BROAD_CATEGORIES
