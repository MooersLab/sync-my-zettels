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
