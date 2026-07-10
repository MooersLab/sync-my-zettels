from sync_my_zettels.links import (
    _Resolver,
    _repair_org_file,
    _repair_md_file,
)


def test_resolver_prefers_address_then_unique_title():
    r = _Resolver()
    r.add("1.14", "1.14 Quantum Crystallography", "ID-A")
    r.add("101.", "101. index of manuscripts in preparation", "ID-B")
    # exact address wins, in either canonical or bare form
    assert r.resolve("1.14 Quantum Crystallography") == "ID-A"
    assert r.resolve("1.14 anything at all") == "ID-A"
    # title fallback when the target carries no usable address
    assert r.resolve("index of manuscripts in preparation") == "ID-B"
    # unknown target does not resolve
    assert r.resolve("something entirely absent") is None


def test_resolver_title_fallback_refuses_to_guess_between_collisions():
    r = _Resolver()
    r.add(None, "Emacs", "ID-1")
    r.add(None, "Emacs", "ID-2")
    # an ambiguous title must not resolve to either
    assert r.resolve("Emacs") is None


def test_repair_org_rewrites_plain_link_to_id(tmp_path):
    r = _Resolver()
    r.add("116.1", "116.1 Emacs", "EMACS-ID")
    f = tmp_path / "note.org.port-review"
    f.write_text("See [[116.1 Emacs][116.1 Emacs]] here.\n", encoding="utf-8")
    new, changed = _repair_org_file(f, r, [], [])
    assert changed
    assert "[[id:EMACS-ID][116.1 Emacs]]" in new


def test_repair_org_leaves_unresolved_and_reports_it(tmp_path):
    r = _Resolver()
    f = tmp_path / "note.org.port-review"
    f.write_text("Link to [[99.9 Nowhere][99.9 Nowhere]].\n", encoding="utf-8")
    unresolved = []
    new, changed = _repair_org_file(f, r, [], unresolved)
    assert not changed
    assert "[[99.9 Nowhere][99.9 Nowhere]]" in new  # left verbatim
    assert unresolved and unresolved[0]["target"] == "99.9 Nowhere"


def test_repair_md_rewrites_wikilink_to_carry_address(tmp_path):
    r = _Resolver()
    r.add("101.", "101. Manuscripts in Preparation", "101. Manuscripts in Preparation")
    f = tmp_path / "n.md.port-review"
    f.write_text("---\ntitle: 5.2 Some note\n---\n\nsee [[index of manuscripts in preparation]]\n",
                 encoding="utf-8")
    # give the resolver a title-key hit for the bare description
    r.add(None, "index of manuscripts in preparation", "101. Manuscripts in Preparation")
    new, changed = _repair_md_file(f, r, [], [])
    assert changed
    assert "[[101. Manuscripts in Preparation|index of manuscripts in preparation]]" in new


def test_repair_md_resolves_generic_parent_note_structurally(tmp_path):
    """org-roam parent backlinks read 'Parent note' with no address; the parent
    is the folgezettel parent of the containing note."""
    r = _Resolver()
    r.add("1.10", "1.10 Experimental phasing", "1.10 Experimental phasing")
    f = tmp_path / "child.md.port-review"
    f.write_text("---\ntitle: 1.10m subsubsubindex of One-shot PSAD\n---\n\n"
                 "* Parent Note\n[[Parent note]]\n", encoding="utf-8")
    new, changed = _repair_md_file(f, r, [], [])
    assert changed
    assert "[[1.10 Experimental phasing|Parent note]]" in new


def test_repair_md_leaves_already_correct_wikilink(tmp_path):
    r = _Resolver()
    r.add("1.10", "1.10 Experimental phasing", "1.10 Experimental phasing")
    f = tmp_path / "n.md.port-review"
    f.write_text("---\ntitle: 2.1 X\n---\n\n[[1.10 Experimental phasing]]\n", encoding="utf-8")
    new, changed = _repair_md_file(f, r, [], [])
    # target already equals the canonical stem -> no rewrite
    assert not changed
    assert "[[1.10 Experimental phasing]]" in new
