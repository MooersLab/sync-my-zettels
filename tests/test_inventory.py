from pathlib import Path

import pytest

from sync_my_zettels.config import Config
from sync_my_zettels import inventory


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def config(tmp_path):
    return Config(
        obsidian_vault=FIXTURES / "obsidian",
        org_roam_vault=FIXTURES / "org-roam",
        root_index_file=FIXTURES / "obsidian" / "00.0 Index of indices.md",
        state_dir=tmp_path,
    )


def test_inventory_walks_both_vaults(config):
    payload = inventory.run(config)
    sides = {r["side"] for r in payload["records"]}
    assert sides == {"obsidian", "org-roam"}


def test_inventory_canonicalizes_roots(config):
    payload = inventory.run(config)
    fz_by_path = {Path(r["path"]).name: r["folgezettel"] for r in payload["records"]}
    assert fz_by_path["1. Crystallography.md"] == "1."
    # Legacy bare-integer org-roam title is canonicalized.
    assert fz_by_path["20240101000001-crystallography.org"] == "1."
    assert fz_by_path["1.1 Diffraction.md"] == "1.1"
    assert fz_by_path["20240101000002-diffraction.org"] == "1.1"


def test_inventory_skips_infrastructure_dirs(tmp_path):
    """templates/ holds org-capture templates, not zettels; never inventory them."""
    org = tmp_path / "org"
    (org / "templates").mkdir(parents=True)
    (org / "20240101000009-real.org").write_text(
        "#+title: 5.1 Real note\n", encoding="utf-8")
    (org / "templates" / "zhub-template.org").write_text(
        "#+title: Template\n", encoding="utf-8")
    cfg = Config(obsidian_vault=tmp_path / "none", org_roam_vault=org,
                 state_dir=tmp_path)
    payload = inventory.run(cfg)
    names = {Path(r["path"]).name for r in payload["records"]}
    assert "20240101000009-real.org" in names
    assert "zhub-template.org" not in names


def test_scan_obsidian_recurses_into_note_subdirs_but_skips_infra(tmp_path):
    """The vault files notes into subdirs; a top-level glob missed them all.

    Recurse into real note dirs (00-Inbox, 70-unindexed) but never into
    template, import, or hidden infrastructure dirs."""
    v = tmp_path / "vault"
    (v / "70-unindexed").mkdir(parents=True)
    (v / "40-Templates").mkdir()
    (v / ".obsidian").mkdir()
    (v / "org-roam-import").mkdir()
    (v / "1.1 Root note.md").write_text("body\n", encoding="utf-8")
    (v / "70-unindexed" / "5.2 Deep note.md").write_text("body\n", encoding="utf-8")
    (v / "40-Templates" / "note template.md").write_text("body\n", encoding="utf-8")
    (v / ".obsidian" / "plugin note.md").write_text("body\n", encoding="utf-8")
    (v / "org-roam-import" / "9.9 Imported.md").write_text("body\n", encoding="utf-8")
    names = {Path(r.path).name for r in inventory.scan_obsidian(v)}
    assert "1.1 Root note.md" in names          # top level still seen
    assert "5.2 Deep note.md" in names          # subdir now seen
    assert "note template.md" not in names      # template dir skipped
    assert "plugin note.md" not in names        # hidden dir skipped
    assert "9.9 Imported.md" not in names       # import dir skipped


def test_inventory_reports_no_folgezettel_for_orphan(config):
    payload = inventory.run(config)
    orphan = next(
        r for r in payload["records"]
        if Path(r["path"]).name == "20240101000003-orphan.org"
    )
    assert orphan["folgezettel"] is None
    assert orphan["org_roam_id"] == "AAAAAAAA-0000-0000-0000-000000000003"


def test_inventory_captures_id_links(config):
    payload = inventory.run(config)
    diffraction = next(
        r for r in payload["records"]
        if Path(r["path"]).name == "20240101000002-diffraction.org"
    )
    assert "AAAAAAAA-0000-0000-0000-000000000001" in diffraction["outgoing_links"]


def test_inventory_writes_checkpoint(config):
    inventory.run(config)
    assert config.inventory_path().exists()


def test_obsidian_address_comes_from_filename_not_title(tmp_path):
    """Obsidian keeps the folgezettel in the filename; the H1 title omits it."""
    from sync_my_zettels.inventory import scan_obsidian
    v = tmp_path / "vault"; v.mkdir()
    (v / "1.12c5 Assembling Table 2.md").write_text("# Assembling Table 2\n\nbody\n")
    rec = list(scan_obsidian(v))[0]
    assert rec.folgezettel == "1.12c5"      # not "2." from 'Table 2'
    assert rec.title == "Assembling Table 2"


def test_org_roam_address_only_from_title_keyword(tmp_path):
    """A timestamped stem must never yield an address."""
    from sync_my_zettels.inventory import scan_org_roam
    v = tmp_path / "org"; v.mkdir()
    (v / "20210316104407-https_www_bing.org").write_text("body only, no title keyword\n")
    (v / "20240101000001-quantum.org").write_text("#+title: 1.14 Quantum Crystallography\n")
    recs = {r.path.split("/")[-1]: r for r in scan_org_roam(v)}
    assert recs["20210316104407-https_www_bing.org"].folgezettel is None
    assert recs["20240101000001-quantum.org"].folgezettel == "1.14"


def test_normalize_title_strips_index_prefix_like_title_core():
    """The two matching passes must normalize identically, or a root worded
    'X' in one vault and 'index of X' in the other drifts into a duplicate.
    Regression for the 1. Crystallography / 1. index of crystallography split.
    """
    from sync_my_zettels.inventory import normalize_title
    from sync_my_zettels.matching import title_core
    pairs = [
        ("1. Crystallography", "1. index of crystallography"),
        ("115. Protocols", "115. index of protocols"),
        ("30. Knowledge Management", "subindex of knowledge management"),
    ]
    for a, b in pairs:
        assert normalize_title(a) == normalize_title(b), (a, b)
        # and the two functions agree with each other
        assert normalize_title(a) == title_core(a).replace(" ", "").replace("-", "")
    # a genuinely different topic must NOT collapse together
    assert normalize_title("1. Crystallography") != normalize_title("2. Protein Chemistry")
