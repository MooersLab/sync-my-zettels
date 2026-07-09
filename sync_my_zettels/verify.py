"""Phase 8: verify the reconciled state.

Calls ``emacs --batch`` to run ``org-roam-db-sync``, reruns the
inventory and matching phases, and reports the remaining counts of
matched, unpaired, and folgezettel-less notes. The reconciliation is
considered clean when ``obsidian_only`` and ``org_roam_only`` are
empty and every record carries a canonical folgezettel.

The emacs shell-out is deferred; for now the phase reruns inventory
plus matching and writes a summary report.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from . import inventory, matching


def run(config: Config) -> dict:
    inventory.run(config)
    match_payload = matching.run(config)

    inv = json.loads(config.inventory_path().read_text(encoding="utf-8"))
    without_fz = [r for r in inv["records"] if not r.get("folgezettel")]

    payload = {
        "version": 1,
        "matched": len(match_payload["matched"]),
        "obsidian_only": len(match_payload["obsidian_only"]),
        "org_roam_only": len(match_payload["org_roam_only"]),
        "ambiguous": len(match_payload["ambiguous"]),
        "without_folgezettel": len(without_fz),
        "clean": (
            len(match_payload["obsidian_only"]) == 0
            and len(match_payload["org_roam_only"]) == 0
            and len(match_payload["ambiguous"]) == 0
            and len(without_fz) == 0
        ),
        "note": (
            "This phase currently reruns inventory and matching. The next "
            "iteration shells out to emacs --batch for org-roam-db-sync "
            "and runs autoslip-roam validation across every .org file."
        ),
    }
    config.ensure_state_dir()
    config.verify_path().write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload
