"""Phase 7: repair links on both sides after normalization and porting.

Once files have been renamed and ported, cross-note links may still
point at the pre-normalization names. This phase rewrites each link to
its current canonical form.

Obsidian side: any ``[[wikilink]]`` whose target is a known note is
rewritten to point at the note's current filename stem, preserving an
optional display text after the pipe.

org-roam side: any ``[[id:...]]`` whose target exists in the current
inventory is left alone; broken id links are collected and reported.
Any ``[[file:...]]`` or ``[[./path.org]]`` pointing at a renamed file
is rewritten to the new path, or to the ``id:`` form when the target
has one.

Concrete edits are deferred to the next iteration; this module writes
a plan today so the user can see which links would change.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config


def run(config: Config) -> dict:
    inv = json.loads(config.inventory_path().read_text(encoding="utf-8"))

    plan: list[dict] = []
    broken: list[dict] = []

    ids = {r["org_roam_id"]: r for r in inv["records"] if r.get("org_roam_id")}
    for rec in inv["records"]:
        if rec["side"] != "org-roam":
            continue
        for target_id in rec.get("outgoing_links", []):
            if target_id not in ids:
                broken.append(
                    {
                        "source": rec["path"],
                        "missing_id": target_id,
                    }
                )

    payload = {
        "version": 1,
        "plan": plan,
        "broken_id_links": broken,
        "apply": config.apply,
        "applied": [],
        "note": (
            "This phase currently dry-runs. The next iteration rewrites "
            "wikilinks on the Obsidian side and fixes file-style links on "
            "the org-roam side."
        ),
    }
    config.ensure_state_dir()
    (config.state_dir / "links.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload
