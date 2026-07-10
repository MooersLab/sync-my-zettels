import re

from sync_my_zettels.port import (
    split_yaml,
    split_org_header,
    slugify,
    obsidian_filename,
    org_filename,
    protect_links,
    restore_links,
    wikilink_to_org,
    org_id_link_to_wikilink,
    WIKILINK_RE,
    ORG_ID_LINK_RE,
)


def test_split_yaml_extracts_frontmatter_and_body():
    meta, body = split_yaml('---\ntitle: 1.14 Quantum\nsource: org-roam\n---\n\nhello\n')
    assert meta["title"] == "1.14 Quantum"
    assert meta["source"] == "org-roam"
    assert body.strip() == "hello"


def test_split_yaml_passthrough_when_absent():
    meta, body = split_yaml("no frontmatter\n")
    assert meta == {} and body == "no frontmatter\n"


def test_split_org_header_pulls_id_and_title_and_strips_keywords():
    text = (":PROPERTIES:\n:ID:       ABC-123\n:END:\n"
            "#+title: 1.14 Quantum Crystallography\n#+filetags: :zhub:\n\nbody here\n")
    org_id, title, body = split_org_header(text)
    assert org_id == "ABC-123"
    assert title == "1.14 Quantum Crystallography"
    assert body.strip() == "body here"
    assert "#+title" not in body and ":ID:" not in body


def test_split_org_header_without_drawer():
    org_id, title, body = split_org_header("#+title: 8.1 Nim\n\nx\n")
    assert org_id is None and title == "8.1 Nim"


def test_filenames_follow_each_vault_convention():
    # Obsidian: '<address> <title>.md' — the title already carries the address
    assert obsidian_filename("1.14 Quantum Crystallography") == "1.14 Quantum Crystallography.md"
    # path separators must never leak into a filename
    assert "/" not in obsidian_filename("7/3 Docking")
    # org-roam: '<timestamp>-<addr_slug>_<slug>.org'
    assert org_filename("20240101000001", "1.14", "Quantum Crystallography") == (
        "20240101000001-1_14_quantum_crystallography.org")
    assert org_filename("20240101000001", None, "No Address").startswith("20240101000001-no_address")


def test_slugify_is_bounded_and_safe():
    assert slugify("Hello, World!") == "hello_world"
    assert len(slugify("x" * 200)) <= 48


def test_links_survive_a_pandoc_round_trip_via_placeholders():
    """Placeholders must be opaque to a converter and restorable afterwards."""
    md = "see [[1.14 quantum crystallography]] and [[1. crystallography|crys]]"
    protected, stash = protect_links(md, WIKILINK_RE)
    assert "[[" not in protected and len(stash) == 2
    # simulate a converter mangling everything except the placeholders
    restored = restore_links(protected, stash, wikilink_to_org)
    assert "[[1.14 quantum crystallography][1.14 quantum crystallography]]" in restored
    assert "[[1. crystallography][crys]]" in restored


def test_org_id_links_become_wikilinks():
    org = "see [[id:A77F-1][1.14 Quantum Crystallography]] here"
    protected, stash = protect_links(org, ORG_ID_LINK_RE)
    assert "id:" not in protected and len(stash) == 1
    restored = restore_links(protected, stash, org_id_link_to_wikilink)
    assert restored == "see [[1.14 Quantum Crystallography]] here"


# --- regressions found by the first pilot run -------------------------------

def test_master_address_is_forced_back_onto_the_title():
    """Obsidian keeps the address in the FILENAME; its YAML title omits it.

    Without this, 1125 ported notes would land in org-roam with no folgezettel.
    """
    from sync_my_zettels.port import title_with_address
    assert title_with_address("About pKa values of amino acids", "1.2e8") == (
        "1.2e8 About pKa values of amino acids")
    # already present -> not duplicated
    assert title_with_address("1.14 Quantum Crystallography", "1.14") == (
        "1.14 Quantum Crystallography")
    assert title_with_address("No address", None) == "No address"


def test_org_filename_does_not_repeat_the_address():
    """Pilot produced '...-127_2_127_2_accessing_data...'."""
    got = org_filename("20260301211122", "127.2", "127.2 Accessing data on ourdisk")
    assert got == "20260301211122-127_2_accessing_data_on_ourdisk.org"
    assert got.count("127_2") == 1


def test_strip_leading_h1_only_when_it_repeats_the_title():
    from sync_my_zettels.port import strip_leading_h1
    body = "# About pKa values of amino acids\n\ntext\n"
    assert strip_leading_h1(body, "1.2e8 About pKa values of amino acids").startswith("text")
    # a different H1 is real content and must survive
    keep = "# Methods\n\ntext\n"
    assert strip_leading_h1(keep, "1.2e8 About pKa") == keep


def test_markdown_note_links_are_converted_not_mangled():
    """Pilot produced [[file:1.2e%20Amino%20acids.md][...]]."""
    from sync_my_zettels.port import MD_ANY_LINK_RE, md_link_render
    md = "- [1.2e Amino acids](1.2e%20Amino%20acids.md)\n- [[1. crystallography]]"
    protected, stash = protect_links(md, MD_ANY_LINK_RE)
    assert "](" not in protected and "[[" not in protected and len(stash) == 2
    out = restore_links(protected, stash, md_link_render)
    assert "[[1.2e Amino acids][1.2e Amino acids]]" in out   # url-decoded, .md dropped
    assert "[[1. crystallography][1. crystallography]]" in out


def test_headings_are_promoted_when_the_duplicate_h1_is_dropped():
    from sync_my_zettels.port import promote_headings
    assert promote_headings("## Parent Note\n### Sub\n") == "# Parent Note\n## Sub\n"
    # a lone '#' is already level 1 and must not lose its marker
    assert promote_headings("# Keep\n") == "# Keep\n"


def test_split_org_header_preserves_code_blocks():
    """A blanket '^#\\+' sweep ate #+begin_src/#+end_src, spilling code into prose.

    That silently corrupted every code block and made pandoc choke on the
    leaked elisp/LaTeX/shell. Only the LEADING keyword run may be stripped.
    """
    src = ("#+title: T\n#+filetags: :x:\n\nIntro.\n\n"
           "#+begin_src python\nprint(\"hi\")\n#+end_src\n")
    _, title, body = split_org_header(src)
    assert title == "T"
    assert "#+begin_src python" in body and "#+end_src" in body
    assert "#+title" not in body and "#+filetags" not in body
    assert body.startswith("Intro.")


def test_conversion_failure_preserves_the_body_instead_of_dropping_it():
    from sync_my_zettels.port import convert_or_preserve
    ok, err = convert_or_preserve("plain text\n", "gfm", "org-auto_identifiers", fence="md")
    assert err is None and "plain text" in ok
    # an unparseable format name forces the failure path
    out, err = convert_or_preserve("raw \\paragraph{x}\n", "gfm", "not-a-format", fence="md")
    assert err is not None
    assert out.startswith("```org") and "\\paragraph{x}" in out   # nothing lost
