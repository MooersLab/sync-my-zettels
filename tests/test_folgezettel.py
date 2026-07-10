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


def test_extract_is_anchored_not_a_search():
    """A number anywhere in the title must NOT become an address.

    These are real failures observed in the vaults: 'Table 2' -> '2.',
    '310-helix' -> '310.', '3-dimensional' -> '3.', and org-roam timestamp
    stems -> a 14-digit 'address'.
    """
    assert extract_from_title("Assembling Table 2") is None
    assert extract_from_title("The 310-helix the pi-helix") is None
    assert extract_from_title("Nomenclature of 3-dimensional lattices") is None
    assert extract_from_title("biomedicine 2021 march 18") is None
    assert extract_from_title("DISC 100-word biography") is None
    assert extract_from_title("IUCr Biography 2025") is None
    assert extract_from_title("20210316104407-https_www_bing_com") is None
    assert extract_from_title("3203Emacsconf2021 Reproducible graphics") is None


def test_extract_requires_a_separator_after_the_address():
    assert extract_from_title("1.12c5 Assembling Table 2") == "1.12c5"
    assert extract_from_title("1.2d2 The 310-helix") == "1.2d2"
    assert extract_from_title("127. 6564XrayDataArchiving") == "127."
    assert extract_from_title("00.0 Index of indices") == "00.0"
    assert extract_from_title("1.14l1 Deep leaf") == "1.14l1"
