"""Phase 6: create the missing counterpart for every unpaired note.

Obsidian-only notes are converted with ``pandoc -f markdown -t org`` and
written under the org-roam vault with a canonical filename. A top-level
property drawer is prepended carrying a freshly minted ``:ID:`` so
org-roam indexes the new file as a node.

org-roam-only notes are converted with ``pandoc -f org -t markdown_strict``
and written under the Obsidian vault with a canonical filename and a
YAML frontmatter block containing the folgezettel prefix and any tags.

Because pandoc round trips are lossy for a few org constructs, newly
ported files land with a ``.port-review`` suffix on the first pass.
The user reviews and then renames to drop the suffix.

Wiring up pandoc and the ID/wikilink translation is deferred to the
next iteration. This module currently produces a JSON plan the plugin
uses to show the user what will move where.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .config import Config


def _new_org_id() -> str:
    return str(uuid.uuid4()).upper()


def run(config: Config) -> dict:
    matches = json.loads(config.matches_path().read_text(encoding="utf-8"))

    plan: list[dict] = []
    for rec in matches["obsidian_only"]:
        plan.append(
            {
                "kind": "port-to-org",
                "source": rec["path"],
                "proposed_id": _new_org_id(),
                "folgezettel": rec.get("folgezettel"),
            }
        )
    for rec in matches["org_roam_only"]:
        plan.append(
            {
                "kind": "port-to-obsidian",
                "source": rec["path"],
                "folgezettel": rec.get("folgezettel"),
            }
        )

    payload = {
        "version": 1,
        "plan": plan,
        "apply": config.apply,
        "applied": [],
        "note": (
            "This phase currently dry-runs. The next iteration calls pypandoc "
            "per row, writes the converted file with a .port-review suffix, "
            "and translates links in a follow-up pass."
        ),
    }
    config.ensure_state_dir()
    (config.state_dir / "port.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload
