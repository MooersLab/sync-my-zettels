"""Phase 5: normalize org-roam filenames and titles to the master addresses.

For every paired org-roam note whose folgezettel differs from the
Obsidian master, and for every confirmed assignment from phase 4,
rewrite the ``#+title:`` keyword, rename the file on disk, and update
the old parent's forward-link section and the child's backlink.

The heavy lifting is delegated to emacs batch mode running
``autoslip-roam-reparent-subtree``, so the rename semantics match the
behavior users already see from the autoslip-roam commands.

This module is a stub: the function signature is fixed, but the emacs
shell-out is wired up in a later pass. For now ``run`` collects the
set of changes it would make and writes them as a plan JSON so the
plugin can preview them.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config


def run(config: Config) -> dict:
    matches = json.loads(config.matches_path().read_text(encoding="utf-8"))
    assignments = json.loads(config.assignments_path().read_text(encoding="utf-8"))

    plan: list[dict] = []
    for pair in matches["matched"]:
        left = pair["obsidian"]
        right = pair["org_roam"]
        if left.get("folgezettel") and left["folgezettel"] != right.get("folgezettel"):
            plan.append(
                {
                    "kind": "retitle",
                    "path": right["path"],
                    "old_folgezettel": right.get("folgezettel"),
                    "new_folgezettel": left["folgezettel"],
                    "source": "obsidian-master",
                }
            )
    for row in assignments.get("confirmed", []):
        plan.append(
            {
                "kind": "retitle",
                "path": row["path"],
                "old_folgezettel": None,
                "new_folgezettel": row["address"],
                "source": "confirmed-assignment",
            }
        )

    payload = {
        "version": 1,
        "plan": plan,
        "apply": config.apply,
        "applied": [],
        "note": (
            "This phase currently dry-runs. The next iteration shells out to "
            "emacs --batch and calls autoslip-roam-reparent-subtree per row."
        ),
    }
    config.ensure_state_dir()
    (config.state_dir / "normalize.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload
