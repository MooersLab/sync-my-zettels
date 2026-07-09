"""Phase 2: extract the master root-node list from the Obsidian index file.

Reads ``00.0 Index of indices.md`` (the path is configurable) and yields
a list of (address, topic) pairs that every subsequent phase consults
when it needs to know the authoritative root numbers.

The parser accepts lines in any of these forms::

    - 1. Crystallography
    - [[1. Crystallography]]
    1. Crystallography
    [[1. Crystallography]]
    [1. Crystallography](1.%20Crystallography.md)

The last form is an Obsidian Markdown link, which is how the vault's
own index file is written.  It requires a leading integer and a
trailing period on the root, and ignores any line that does not match.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Config


ROOT_LINE_RE = re.compile(
    r"""
    ^\s*                          # leading whitespace
    (?:[-*]\s*)?                  # optional bullet
    (?:\[\[|\[)?                  # optional wikilink [[ or Markdown-link [ open
    (?P<address>[0-9]+)\.\s+      # integer + period + space
    (?P<topic>[^\]\n]+?)          # topic text (up to ] or newline)
    (?:                           # optional closer:
        \]\]                      #   wikilink close ]]
      | \]\([^)\n]*\)             #   Markdown-link close ](target)
    )?
    \s*$
    """,
    re.VERBOSE | re.MULTILINE,
)


@dataclass
class RootEntry:
    address: str  # canonical form with trailing period, e.g. "1."
    topic: str


def parse_root_index(text: str) -> list[RootEntry]:
    entries: list[RootEntry] = []
    seen: set[str] = set()
    for match in ROOT_LINE_RE.finditer(text):
        addr = match.group("address") + "."
        if addr in seen:
            continue
        seen.add(addr)
        entries.append(RootEntry(address=addr, topic=match.group("topic").strip()))
    entries.sort(key=lambda e: int(e.address.rstrip(".")))
    return entries


def run(config: Config) -> dict:
    path = config.root_index_file
    if not path.exists():
        raise FileNotFoundError(
            f"Root-node index not found at {path}. "
            "Create it in the Obsidian vault with lines of the form '1. Topic Name'."
        )
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    entries = parse_root_index(text)
    payload = {
        "version": 1,
        "source": str(path),
        "roots": [asdict(e) for e in entries],
    }
    config.ensure_state_dir()
    config.roots_path().write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload
