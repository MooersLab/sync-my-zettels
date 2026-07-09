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
