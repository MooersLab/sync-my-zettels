from sync_my_zettels.folgezettel import (
    canonicalize_root,
    extract_from_title,
    is_root_address,
    parse_parent,
)


def test_is_root_address_accepts_both_forms():
    assert is_root_address("1")
    assert is_root_address("1.")
    assert is_root_address("42")
    assert is_root_address("42.")
    assert not is_root_address("1.2")
    assert not is_root_address("1.2a")
    assert not is_root_address("")


def test_canonicalize_root():
    assert canonicalize_root("1") == "1."
    assert canonicalize_root("1.") == "1."
    assert canonicalize_root("1.2") == "1.2"
    assert canonicalize_root("1.2a") == "1.2a"
    assert canonicalize_root(None) is None


def test_extract_from_title_canonicalizes_roots():
    assert extract_from_title("1 Introduction") == "1."
    assert extract_from_title("1. Introduction") == "1."
    assert extract_from_title("1.2 Subtopic") == "1.2"
    assert extract_from_title("1.2a3 Deep") == "1.2a3"
    assert extract_from_title("No address here") is None


def test_parse_parent_mirrors_autoslip_grammar():
    assert parse_parent("1.2a3b") == "1.2a3"
    assert parse_parent("1.2a3") == "1.2a"
    assert parse_parent("1.2a") == "1.2"
    assert parse_parent("1.2") == "1."
    assert parse_parent("1.") is None
    assert parse_parent("1") is None
    assert parse_parent(None) is None
