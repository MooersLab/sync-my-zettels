"""Phase 1: walk both vaults and record every note's identity.

Reads every *.md at the top level of the Obsidian vault and every *.org
under the org-roam vault (top level plus subfolders). For each note it
records the file path, side, title, folgezettel address, normalized
title (for matching), outgoing links, and a sha256 of the body.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .config import Config
from .folgezettel import canonicalize_root, extract_from_title


TITLE_KEYWORD_RE = re.compile(r"^\s*#\+title:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
ID_PROPERTY_RE = re.compile(r"^\s*:ID:\s*(\S+)\s*$", re.IGNORECASE | re.MULTILINE)
YAML_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
YAML_TITLE_RE = re.compile(r"^\s*title:\s*['\"]?(.+?)['\"]?\s*$", re.IGNORECASE | re.MULTILINE)
MD_H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+?)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")
ID_LINK_RE = re.compile(r"\[\[id:([0-9a-fA-F-]+)\]")
NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class NoteRecord:
    """One row in the inventory."""

    path: str
    side: str  # "obsidian" or "org-roam"
    title: Optional[str]
    folgezettel: Optional[str]
    normalized_title: str
    org_roam_id: Optional[str]
    outgoing_links: list[str] = field(default_factory=list)
    content_sha256: str = ""
    byte_size: int = 0


def normalize_title(title: Optional[str]) -> str:
    """Collapse a title down to lowercase alphanumerics for matching.

    Strips a leading folgezettel address, case-folds, drops all
    non-alphanumeric characters. Two notes whose titles match under this
    transform are considered the same note for pair-matching purposes.
    """
    if not title:
        return ""
    # Drop a leading folgezettel prefix (``1.``, ``1.2a3``, etc.) and any
    # trailing separator.
    stripped = re.sub(
        r"\A[0-9]+(?:[.][0-9]+)*(?:[a-z]+(?:[0-9]+)?)*[.\s\-_]*",
        "",
        title.strip(),
    )
    return NORMALIZE_RE.sub("", stripped.lower())


def _sha256(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _obsidian_title(body: str, fallback_stem: str) -> Optional[str]:
    """Pick the best title signal for a markdown note.

    Preference order: YAML ``title:`` field, first H1, the filename stem.
    """
    frontmatter = YAML_FRONTMATTER_RE.match(body)
    if frontmatter:
        yt = YAML_TITLE_RE.search(frontmatter.group(1))
        if yt:
            return yt.group(1).strip()
    h1 = MD_H1_RE.search(body)
    if h1:
        return h1.group(1).strip()
    return fallback_stem or None


def _org_title(body: str, fallback_stem: str) -> Optional[str]:
    """Pick the best title signal for an org-roam note.

    Preference order: ``#+title:`` keyword, then the filename stem.
    """
    match = TITLE_KEYWORD_RE.search(body)
    if match:
        return match.group(1).strip()
    return fallback_stem or None


def _obsidian_outgoing(body: str) -> list[str]:
    return [m.group(1).strip() for m in WIKILINK_RE.finditer(body)]


def _org_outgoing(body: str) -> list[str]:
    return [m.group(1) for m in ID_LINK_RE.finditer(body)]


def scan_obsidian(vault: Path) -> Iterable[NoteRecord]:
    """Yield a NoteRecord for every top-level ``*.md`` in VAULT."""
    if not vault.exists():
        return
    for path in sorted(vault.glob("*.md")):
        if path.name.startswith("."):
            continue
        body = _read_text(path)
        stem = path.stem
        title = _obsidian_title(body, stem)
        # The Obsidian vault carries the folgezettel in the FILENAME
        # ("1.12c5 Assembling Table 2.md"); its YAML/H1 title usually omits
        # the address. Read the filename first, fall back to the title.
        fz = extract_from_title(stem) or extract_from_title(title)
        fz = canonicalize_root(fz)
        yield NoteRecord(
            path=str(path),
            side="obsidian",
            title=title,
            folgezettel=fz,
            normalized_title=normalize_title(title or stem),
            org_roam_id=None,
            outgoing_links=_obsidian_outgoing(body),
            content_sha256=_sha256(body),
            byte_size=len(body),
        )


def scan_org_roam(vault: Path) -> Iterable[NoteRecord]:
    """Yield a NoteRecord for every ``*.org`` under VAULT (recursive)."""
    if not vault.exists():
        return
    for path in sorted(vault.rglob("*.org")):
        if path.name.startswith("."):
            continue
        body = _read_text(path)
        stem = path.stem
        title = _org_title(body, stem)
        # org-roam filenames are timestamp-slugged (e.g. ``20240101000001-foo.org``)
        # so the filename stem never carries a folgezettel address. Only the
        # ``#+title:`` keyword is authoritative -- read it directly rather than
        # via `title`, which falls back to the stem when the keyword is absent.
        title_keyword = TITLE_KEYWORD_RE.search(body)
        fz = extract_from_title(title_keyword.group(1).strip()) if title_keyword else None
        fz = canonicalize_root(fz)
        id_match = ID_PROPERTY_RE.search(body)
        yield NoteRecord(
            path=str(path),
            side="org-roam",
            title=title,
            folgezettel=fz,
            normalized_title=normalize_title(title or stem),
            org_roam_id=id_match.group(1) if id_match else None,
            outgoing_links=_org_outgoing(body),
            content_sha256=_sha256(body),
            byte_size=len(body),
        )


def run(config: Config) -> dict:
    """Produce the inventory dict and write it to ``inventory.json``."""
    records: list[NoteRecord] = []
    records.extend(scan_obsidian(config.obsidian_vault))
    records.extend(scan_org_roam(config.org_roam_vault))
    payload = {
        "version": 1,
        "obsidian_vault": str(config.obsidian_vault),
        "org_roam_vault": str(config.org_roam_vault),
        "records": [asdict(r) for r in records],
    }
    config.ensure_state_dir()
    config.inventory_path().write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload
