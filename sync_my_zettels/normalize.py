"""Phase 5: normalize org-roam filenames and titles to the master addresses.

For every paired org-roam note whose folgezettel differs from the
Obsidian master, and for every confirmed assignment from phase 4,
rewrite the ``#+title:`` keyword, rename the file on disk, and update
the old parent's forward-link section and the child's backlink.

The heavy lifting is delegated to Emacs running autoslip-roam's own
``autoslip-roam-reparent`` / ``autoslip-roam-reparent-subtree`` commands
under ``emacsclient``, so the rename semantics match the behavior users
already see interactively.

The plan is built and grouped in pure Python (``build_plan`` /
``group_subtrees``) so it can be previewed and unit-tested without Emacs.
A row is folded into a subtree only when its address is a folgezettel
descendant of an in-plan ancestor *and* the remap is prefix-consistent;
this lets a single subtree reparent carry every leaf instead of issuing
one doomed call per leaf. Lone rows use the single-node reparent, which
never drags unrelated same-prefix notes along.

Rows whose note has no current folgezettel (confirmed assignments) cannot
be reparented and are reported as unsupported; assigning a brand-new
address is the ``assign`` phase's job.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import Config
from .folgezettel import parse_parent

ELISP_DRIVER = Path(__file__).parent / "elisp" / "normalize-apply.el"


def build_plan(matches: dict, assignments: dict) -> list[dict]:
    """Return the ordered list of retitle rows from matches + assignments."""
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
    return plan


def _ancestors(address: str) -> list[str]:
    """Return ADDRESS's folgezettel ancestors, nearest first."""
    out: list[str] = []
    parent = parse_parent(address)
    while parent:
        out.append(parent)
        parent = parse_parent(parent)
    return out


def group_subtrees(rows: list[dict]) -> list[dict]:
    """Collapse reparentable ROWS into subtree groups.

    ROWS must all carry an ``old_folgezettel``. A row is folded under the
    nearest in-plan ancestor whose remap is prefix-consistent; the
    remaining rows become group roots. Each returned group is
    ``{"root": row, "leaves": [row, ...]}`` where a nonempty ``leaves``
    marks a genuine subtree move.
    """
    by_old = {r["old_folgezettel"]: r for r in rows}
    leaf_of: dict[str, str] = {}
    for r in rows:
        old = r["old_folgezettel"]
        for anc in _ancestors(old):
            root = by_old.get(anc)
            if root and r["new_folgezettel"] == root["new_folgezettel"] + old[len(anc):]:
                leaf_of[old] = anc
                break
    groups: list[dict] = []
    for r in rows:
        old = r["old_folgezettel"]
        if old in leaf_of:
            continue
        leaves = [x for x in rows if leaf_of.get(x["old_folgezettel"]) == old]
        groups.append({"root": r, "leaves": leaves})
    return groups


def _driver_groups(groups: list[dict]) -> list[dict]:
    """Flatten grouping into the request payload the elisp driver reads."""
    out: list[dict] = []
    for g in groups:
        root = g["root"]
        leaves = g["leaves"]
        out.append(
            {
                "root_path": root["path"],
                "old_address": root["old_folgezettel"],
                "new_address": root["new_folgezettel"],
                "mode": "subtree" if leaves else "single",
                "leaves": [leaf["old_folgezettel"] for leaf in leaves],
            }
        )
    return out


def _elisp_string(value: str) -> str:
    """Quote VALUE as an elisp string literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _run_emacs_driver(config: Config, driver_groups: list[dict]) -> list[dict]:
    """Invoke the elisp driver over emacsclient and return its results.

    This is the single Emacs-touching seam; tests monkeypatch it.
    """
    config.ensure_state_dir()
    request = config.state_dir / "normalize-apply-request.json"
    result = config.state_dir / "normalize-apply-result.json"
    request.write_text(
        json.dumps({"groups": driver_groups}, ensure_ascii=False),
        encoding="utf-8",
    )
    if result.exists():
        result.unlink()

    # A single `-e` argument must hold ONE form: emacsclient does not reliably
    # evaluate a second bare sexp appended to the first. Wrap load+call in progn.
    form = "(progn (load {} nil t) (smz-normalize-apply {} {} {}))".format(
        _elisp_string(str(ELISP_DRIVER)),
        _elisp_string(str(request)),
        _elisp_string(str(result)),
        _elisp_string(str(config.autoslip_roam_el)),
    )
    cmd = ["emacsclient", "-s", config.emacs_socket, "-e", form]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if not result.exists():
        raise RuntimeError(
            "emacs normalize driver produced no result file.\n"
            f"command: {' '.join(cmd)}\n"
            f"exit: {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    payload = json.loads(result.read_text(encoding="utf-8"))
    if "error" in payload:
        raise RuntimeError(f"emacs normalize driver failed: {payload['error']}")
    return payload["results"]


def run(config: Config) -> dict:
    matches = json.loads(config.matches_path().read_text(encoding="utf-8"))
    assignments = json.loads(config.assignments_path().read_text(encoding="utf-8"))
    plan = build_plan(matches, assignments)

    reparentable = [r for r in plan if r["old_folgezettel"]]
    unsupported = [r for r in plan if not r["old_folgezettel"]]
    groups = group_subtrees(reparentable)
    driver_groups = _driver_groups(groups)

    applied: list[dict] = []
    skipped: list[dict] = [
        {
            **row,
            "status": "unsupported",
            "message": "note has no current folgezettel; assign an address first",
        }
        for row in unsupported
    ]

    if config.apply:
        for res in _run_emacs_driver(config, driver_groups):
            (applied if res.get("status") == "applied" else skipped).append(res)

    n_subtree = sum(1 for g in driver_groups if g["mode"] == "subtree")
    n_single = sum(1 for g in driver_groups if g["mode"] == "single")
    if config.apply:
        note = (
            f"Applied {len(applied)} of {len(driver_groups)} reparent operations "
            f"via autoslip-roam on emacs socket '{config.emacs_socket}'. "
            f"{len(skipped)} row(s) skipped."
        )
    else:
        note = (
            f"Dry run. {len(driver_groups)} group(s) would be reparented "
            f"({n_subtree} subtree, {n_single} single); {len(unsupported)} row(s) "
            "unsupported (no current address). Re-run with --apply to execute."
        )

    payload = {
        "version": 1,
        "plan": plan,
        "groups": driver_groups,
        "apply": config.apply,
        "applied": applied,
        "skipped": skipped,
        "note": note,
    }
    config.ensure_state_dir()
    (config.state_dir / "normalize.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload
