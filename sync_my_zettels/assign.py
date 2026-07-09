"""Phase 4: propose folgezettel addresses for org-roam notes without one.

This engine-side implementation uses a naive heuristic. It scans the
matches.json bucket ``org_roam_only`` for notes that also lack a
folgezettel in the inventory, then proposes a next available child
under the root whose topic word-overlap with the note's title is
largest. Where no root has any overlap, the proposal is left blank
and the note is marked for manual assignment.

The Claude plugin is expected to call this function to seed proposals
and then ask the LLM to review each blank or uncertain row, using the
root-node list and the note body as context. Confirmed rows are
written to ``assignments.json``; that file is the authoritative input
for the normalization phase.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from .config import Config


WORD_RE = re.compile(r"[a-zA-Z]{3,}")


def _words(text: Optional[str]) -> set[str]:
    if not text:
        return set()
    return {m.group(0).lower() for m in WORD_RE.finditer(text)}


def _next_child(existing: list[str], parent: str) -> str:
    """Return the next ``parent.N`` address not already used."""
    used = set()
    for addr in existing:
        m = re.match(rf"\A{re.escape(parent.rstrip('.'))}\.([0-9]+)\Z", addr)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"{parent.rstrip('.')}.{n}"


def run(config: Config) -> dict:
    inv = json.loads(config.inventory_path().read_text(encoding="utf-8"))
    matches = json.loads(config.matches_path().read_text(encoding="utf-8"))
    roots_payload = json.loads(config.roots_path().read_text(encoding="utf-8"))
    roots = roots_payload["roots"]

    # Index existing first-level addresses per root so we can suggest the
    # next child.
    children_by_root: dict[str, list[str]] = defaultdict(list)
    for rec in inv["records"]:
        fz = rec.get("folgezettel")
        if not fz:
            continue
        m = re.match(r"\A([0-9]+)\.[0-9]+\Z", fz)
        if m:
            children_by_root[m.group(1) + "."].append(fz)

    proposals: list[dict] = []
    for rec in matches["org_roam_only"]:
        if rec.get("folgezettel"):
            continue
        note_words = _words(rec.get("title"))
        best_root = None
        best_score = 0
        for root in roots:
            score = len(note_words & _words(root["topic"]))
            if score > best_score:
                best_score = score
                best_root = root
        if best_root is None:
            proposals.append(
                {
                    "path": rec["path"],
                    "title": rec.get("title"),
                    "proposed_address": None,
                    "reason": "no word overlap with any root topic",
                }
            )
            continue
        next_addr = _next_child(children_by_root[best_root["address"]], best_root["address"])
        children_by_root[best_root["address"]].append(next_addr)
        proposals.append(
            {
                "path": rec["path"],
                "title": rec.get("title"),
                "proposed_address": next_addr,
                "under_root": best_root,
                "score": best_score,
            }
        )

    payload = {
        "version": 1,
        "proposals": proposals,
        "confirmed": [],
    }
    config.ensure_state_dir()
    config.assignments_path().write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload
