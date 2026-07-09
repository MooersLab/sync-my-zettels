from pathlib import Path

import pytest

from sync_my_zettels.config import Config
from sync_my_zettels import roots
from sync_my_zettels.roots import parse_root_index


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def config(tmp_path):
    return Config(
        obsidian_vault=FIXTURES / "obsidian",
        org_roam_vault=FIXTURES / "org-roam",
        root_index_file=FIXTURES / "obsidian" / "00.0 Index of indices.md",
        state_dir=tmp_path,
    )


def test_roots_parses_bulleted_index(config):
    payload = roots.run(config)
    addresses = [r["address"] for r in payload["roots"]]
    topics = [r["topic"] for r in payload["roots"]]
    assert addresses == ["1.", "2.", "3.", "7."]
    assert topics == ["Crystallography", "Structural biology", "RNA structure", "Writing"]


def test_roots_parses_markdown_link_index():
    """The vault's own index is written as Obsidian Markdown links."""
    text = (
        "# 00.0 Index of indices\n\n"
        "This is prose that must not match: topic 3. is mentioned inline.\n\n"
        "## Subject Matter\n"
        "[1. Crystallography](1.%20Crystallography.md)\n"
        "[41. Mathematics](41.%20Mathematics.md)\n"
        "[47. Ethics](47.%20Ethics)\n"          # no .md suffix
        "[46. Agentic programming](46.%20Agentic%20programming.md) \n"  # trailing space
    )
    entries = parse_root_index(text)
    assert [e.address for e in entries] == ["1.", "41.", "46.", "47."]
    assert [e.topic for e in entries] == [
        "Crystallography",
        "Mathematics",
        "Agentic programming",
        "Ethics",
    ]


def test_roots_parses_mixed_forms():
    """Bare, bulleted, wikilink, and Markdown-link forms coexist."""
    text = (
        "1. Bare\n"
        "- 2. Bulleted\n"
        "[[3. Wikilink]]\n"
        "[4. Markdown](4.%20Markdown.md)\n"
    )
    entries = parse_root_index(text)
    assert [e.address for e in entries] == ["1.", "2.", "3.", "4."]
    assert [e.topic for e in entries] == ["Bare", "Bulleted", "Wikilink", "Markdown"]


def test_roots_missing_file_raises(tmp_path):
    config = Config(
        obsidian_vault=tmp_path,
        org_roam_vault=tmp_path,
        root_index_file=tmp_path / "nope.md",
        state_dir=tmp_path,
    )
    with pytest.raises(FileNotFoundError):
        roots.run(config)
