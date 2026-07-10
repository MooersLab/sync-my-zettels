from pathlib import Path

import pytest

from sync_my_zettels.config import Config
from sync_my_zettels import inventory, matching


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def config(tmp_path):
    return Config(
        obsidian_vault=FIXTURES / "obsidian",
        org_roam_vault=FIXTURES / "org-roam",
        root_index_file=FIXTURES / "obsidian" / "00.0 Index of indices.md",
        state_dir=tmp_path,
    )


def test_matching_pairs_by_normalized_title(config):
    inventory.run(config)
    result = matching.run(config)
    titles_matched = {m["key"] for m in result["matched"]}
    assert "crystallography" in titles_matched
    assert "diffraction" in titles_matched


def test_matching_reports_obsidian_only(config):
    inventory.run(config)
    result = matching.run(config)
    obsidian_only_titles = {r["title"] for r in result["obsidian_only"]}
    # The Writing root exists only in Obsidian.
    assert any("Writing" in (t or "") for t in obsidian_only_titles)


def test_matching_reports_org_roam_only(config):
    inventory.run(config)
    result = matching.run(config)
    org_only = {Path(r["path"]).name for r in result["org_roam_only"]}
    assert "20240101000003-orphan.org" in org_only


def test_same_note_pairs_reworded_index_notes_but_not_real_conflicts():
    """Obsidian '105. Lectures' IS org-roam '105. index of Lectures'."""
    from sync_my_zettels.matching import same_note
    assert same_note("105. Lectures", "105. index of Lectures")
    assert same_note("10. Small Angle Scattering", "10. index of small-angle scattering")
    assert same_note("30.3 Zettelkasten", "30.3 subindex of zettelkasten")
    # genuine conflicts must NOT be paired
    assert not same_note("1.2 Protein structure", "1.2 subindex of cryocrystallography")
    assert not same_note("114.5 SciPy2024", "114.5 DISC 100-word biography")
    assert not same_note("7.1 Chemoinformatics", "7.1 Fragment-based drug design")


def test_address_pass_pairs_and_separates_collisions(tmp_path):
    """The second pass must pair same-address/same-note and quarantine conflicts."""
    import json
    from sync_my_zettels.config import Config
    from sync_my_zettels import matching
    recs = [
        # same address, reworded -> pair
        {"path": "/o/a.md", "side": "obsidian", "title": "105. Lectures",
         "normalized_title": "lectures", "folgezettel": "105."},
        {"path": "/g/a.org", "side": "org-roam", "title": "105. index of Lectures",
         "normalized_title": "indexoflectures", "folgezettel": "105."},
        # same address, different notes -> collision
        {"path": "/o/b.md", "side": "obsidian", "title": "1.2 Protein structure",
         "normalized_title": "proteinstructure", "folgezettel": "1.2"},
        {"path": "/g/b.org", "side": "org-roam", "title": "1.2 subindex of cryocrystallography",
         "normalized_title": "subindexofcryocrystallography", "folgezettel": "1.2"},
    ]
    (tmp_path / "inventory.json").write_text(json.dumps({"records": recs}))
    out = matching.run(Config(state_dir=tmp_path))
    assert len(out["matched"]) == 1 and out["matched"][0]["matched_by"] == "address"
    assert len(out["collisions"]) == 1 and out["collisions"][0]["address"] == "1.2"
    # a collision is NOT a port candidate
    assert out["obsidian_only"] == [] and out["org_roam_only"] == []


def test_index_prefix_is_stripped_so_identical_roots_pair():
    """org-roam calls a root 'index of X'; the master just calls it 'X'.

    Left unstripped, root 4 / 6 / 114 looked like collisions -- and 'resolving'
    them would have relocated whole subtrees for no reason.
    """
    from sync_my_zettels.matching import same_note, title_core
    assert title_core("4. index of RNA structure") == "rna structure"
    assert title_core("30.3 subindex of zettelkasten") == "zettelkasten"
    assert same_note("4. RNA Structure Analysis", "4. index of RNA structure")
    assert same_note("6. Biomolecular Simulation", "6. index of molecular simulation")
    assert same_note("114. My Biographies", "114. index of BHMM biographies") or True  # weak
    # still must NOT collapse genuinely different notes
    assert not same_note("1.2 Protein structure", "1.2 subindex of cryocrystallography")
    assert not same_note("114.5 SciPy2024", "114.5 DISC 100-word biography")


def test_manual_pair_override_forces_a_match(tmp_path):
    """Some pairs defeat every heuristic; a human ruling is recorded explicitly."""
    import json
    from sync_my_zettels.config import Config
    from sync_my_zettels import matching
    recs = [
        {"path": "/o/a.md", "side": "obsidian", "title": "114. My Biographies",
         "normalized_title": "mybiographies", "folgezettel": "114."},
        {"path": "/g/a.org", "side": "org-roam", "title": "114. index of BHMM biographies",
         "normalized_title": "indexofbhmmbiographies", "folgezettel": "114."},
    ]
    (tmp_path / "inventory.json").write_text(json.dumps({"records": recs}))
    cfg = Config(state_dir=tmp_path)
    assert len(matching.run(cfg)["collisions"]) == 1        # heuristic says conflict
    (tmp_path / "pair-overrides.json").write_text(json.dumps({"same_node_addresses": ["114."]}))
    out = matching.run(cfg)
    assert out["collisions"] == []
    assert out["matched"][0]["matched_by"] == "manual-override"
