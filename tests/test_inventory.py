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
