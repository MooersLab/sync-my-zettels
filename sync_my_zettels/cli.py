"""Command-line entry point for sync-my-zettels.

Every phase writes its output to ~/.sync-my-zettels/. Phases that
mutate the filesystem only do so when --apply is passed; the default
is a dry run that writes a JSON plan.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from .config import (
    Config,
    DEFAULT_OBSIDIAN_VAULT,
    DEFAULT_ORG_ROAM_VAULT,
    DEFAULT_ROOT_INDEX_FILE,
    DEFAULT_STATE_DIR,
)
from . import inventory, roots, matching, assign, normalize, port, links, verify


PHASES: dict[str, Callable[[Config], dict]] = {
    "inventory": inventory.run,
    "roots": roots.run,
    "match": matching.run,
    "assign": assign.run,
    "normalize": normalize.run,
    "port": port.run,
    "repair-links": links.run,
    "verify": verify.run,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sync-my-zettels",
        description="Reconcile an Obsidian vault and an org-roam zettelkasten.",
    )
    parser.add_argument(
        "phase",
        choices=sorted(PHASES.keys()),
        help="which phase to run",
    )
    parser.add_argument(
        "--obsidian-vault",
        type=Path,
        default=DEFAULT_OBSIDIAN_VAULT,
        help="path to the Obsidian vault (top-level notes scanned)",
    )
    parser.add_argument(
        "--org-roam-vault",
        type=Path,
        default=DEFAULT_ORG_ROAM_VAULT,
        help="path to the org-roam vault (scanned recursively)",
    )
    parser.add_argument(
        "--root-index",
        type=Path,
        default=DEFAULT_ROOT_INDEX_FILE,
        help="path to the Obsidian master root-node index file",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help="directory for JSON checkpoints between phases",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply the phase's proposed changes (default: dry run)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the phase's return value as JSON on stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = Config(
        obsidian_vault=args.obsidian_vault,
        org_roam_vault=args.org_roam_vault,
        root_index_file=args.root_index,
        state_dir=args.state_dir,
        apply=args.apply,
    )
    try:
        result = PHASES[args.phase](config)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.json:
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        _print_summary(args.phase, result, config)
    return 0


def _print_summary(phase: str, result: dict, config: Config) -> None:
    if phase == "inventory":
        n = len(result["records"])
        print(f"inventoried {n} notes ({config.inventory_path()})")
    elif phase == "roots":
        n = len(result["roots"])
        print(f"parsed {n} root entries from {result['source']}")
    elif phase == "match":
        print(
            "match summary: "
            f"{len(result['matched'])} matched, "
            f"{len(result['obsidian_only'])} obsidian-only, "
            f"{len(result['org_roam_only'])} org-roam-only, "
            f"{len(result['ambiguous'])} ambiguous"
        )
    elif phase == "assign":
        print(f"generated {len(result['proposals'])} assignment proposals")
    elif phase == "normalize":
        action = "would change" if not result["apply"] else "changed"
        print(f"{action} {len(result['plan'])} org-roam notes")
    elif phase == "port":
        action = "would port" if not result["apply"] else "ported"
        print(f"{action} {len(result['plan'])} notes")
    elif phase == "repair-links":
        print(
            f"broken id-link count: {len(result['broken_id_links'])}; "
            f"link-rewrite plan size: {len(result['plan'])}"
        )
    elif phase == "verify":
        print(
            "verify: "
            f"matched={result['matched']}, "
            f"obsidian_only={result['obsidian_only']}, "
            f"org_roam_only={result['org_roam_only']}, "
            f"ambiguous={result['ambiguous']}, "
            f"without_folgezettel={result['without_folgezettel']}, "
            f"clean={result['clean']}"
        )


if __name__ == "__main__":
    sys.exit(main())
