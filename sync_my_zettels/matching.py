"""Phase 3: pair Obsidian notes with org-roam notes.

Matches by normalized title first, then by folgezettel address as a
tie-breaker. Produces three buckets in ``matches.json``::

    matched        - both sides have a note for this normalized title
    obsidian_only  - master has it, follower does not (port to org-roam)
    org_roam_only  - follower has it, master does not (port to Obsidian,
                     and maybe also assign a folgezettel)
    ambiguous      - more than one note matched under one normalized key;
                     requires human review

The matching logic is intentionally simple in this first cut. Later
passes can bolt on content-hash fallback and a fuzzy title scorer.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .config import Config


def run(config: Config) -> dict:
    inv_path = config.inventory_path()
    if not inv_path.exists():
        raise FileNotFoundError(
            f"Inventory not found at {inv_path}. Run the inventory phase first."
        )
    inventory = json.loads(inv_path.read_text(encoding="utf-8"))

    by_key_obsidian: dict[str, list[dict]] = defaultdict(list)
    by_key_org: dict[str, list[dict]] = defaultdict(list)
    for record in inventory["records"]:
        key = record["normalized_title"]
        if record["side"] == "obsidian":
            by_key_obsidian[key].append(record)
        else:
            by_key_org[key].append(record)

    matched: list[dict] = []
    obsidian_only: list[dict] = []
    org_roam_only: list[dict] = []
    ambiguous: list[dict] = []

    all_keys = set(by_key_obsidian) | set(by_key_org)
    for key in sorted(all_keys):
        left = by_key_obsidian.get(key, [])
        right = by_key_org.get(key, [])
        if not key:
            # Empty normalized title is never a safe match.
            ambiguous.append({"key": key, "obsidian": left, "org_roam": right})
            continue
        if len(left) > 1 or len(right) > 1:
            ambiguous.append({"key": key, "obsidian": left, "org_roam": right})
            continue
        if left and right:
            matched.append({"key": key, "obsidian": left[0], "org_roam": right[0]})
        elif left:
            obsidian_only.append(left[0])
        elif right:
            org_roam_only.append(right[0])

    payload = {
        "version": 1,
        "matched": matched,
        "obsidian_only": obsidian_only,
        "org_roam_only": org_roam_only,
        "ambiguous": ambiguous,
    }
    config.ensure_state_dir()
    config.matches_path().write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload
