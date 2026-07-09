"""Phase 4b: apply confirmed assignments (give a note its first folgezettel).

The ``assign`` phase proposes a folgezettel for org-roam notes that have
none and records the accepted rows in ``assignments.json`` under
``confirmed``. Those notes have NO current address, so ``normalize`` (which
only reparents an existing address) cannot act on them. This phase fills
that gap.

Giving a note its first address is deliberately simple and done in pure
Python -- edit the ``#+title:`` line to prepend the address, then rename
the file so its slug carries the address -- with Emacs used only to
reconcile the org-roam DB afterward. Parent/child backlink wiring is left
to the ``repair-links`` phase, which exists for exactly that.

Every write is guarded: a note that already carries a folgezettel is left
untouched (never double-address), and a file rename that would clobber an
existing path is skipped.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .config import Config
from .folgezettel import extract_from_title

TITLE_RE = re.compile(r"^(#\+[Tt][Ii][Tt][Ll][Ee]:[ \t]*)(.*)$", re.MULTILINE)
# org-roam slug filenames: <timestamp digits>-<slug>.org
FILENAME_RE = re.compile(r"\A(\d{6,}-)(.*)\Z")


def title_with_address(title: str, address: str) -> str:
    """Prepend ADDRESS to a bare TITLE string."""
    return f"{address} {title}"


def address_filename(path: str, address: str) -> str | None:
    """Return PATH renamed so its slug carries ADDRESS, or None if the
    basename is not an org-roam ``<timestamp>-<slug>`` name."""
    p = Path(path)
    m = FILENAME_RE.match(p.name)
    if not m:
        return None
    addr_slug = address.replace(".", "_")
    new_name = f"{m.group(1)}{addr_slug}_{m.group(2)}"
    return str(p.with_name(new_name))


def _read_title(path: Path) -> str | None:
    """Return the current #+title text of the note at PATH, or None."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = TITLE_RE.search(text)
    return m.group(2).strip() if m else None


def plan_assignments(config: Config) -> list[dict]:
    """Build the per-note plan from assignments.json's confirmed rows.

    Each plan row records the guard verdict so a dry run shows exactly what
    an apply would (and would not) do.
    """
    assignments = json.loads(config.assignments_path().read_text(encoding="utf-8"))
    plan: list[dict] = []
    for row in assignments.get("confirmed", []):
        path = Path(row["path"])
        address = row["address"]
        entry = {"path": str(path), "address": address, "title": row.get("title")}
        if not path.exists():
            entry.update(action="skip", reason="file not found")
            plan.append(entry)
            continue
        current = _read_title(path)
        if current is None:
            entry.update(action="skip", reason="no #+title line")
        elif extract_from_title(current):
            entry.update(
                action="skip",
                reason=f"note already has address {extract_from_title(current)}",
            )
        else:
            new_file = address_filename(str(path), address)
            if new_file and Path(new_file).exists():
                entry.update(action="skip", reason="target filename already exists")
            else:
                entry.update(
                    action="assign",
                    new_title=title_with_address(current, address),
                    new_path=new_file or str(path),
                    renamed=bool(new_file),
                )
        plan.append(entry)
    return plan


def _apply_row(row: dict) -> dict:
    """Perform one assignment's file edits; return the row with an outcome."""
    path = Path(row["path"])
    text = path.read_text(encoding="utf-8", errors="replace")
    new_text, n = TITLE_RE.subn(
        lambda m: f"{m.group(1)}{row['new_title']}", text, count=1
    )
    if n != 1:
        return {**row, "action": "skip", "reason": "title line vanished before write"}
    path.write_text(new_text, encoding="utf-8")
    if row.get("renamed"):
        path.rename(row["new_path"])
    return {**row, "status": "applied"}


def _reconcile_db(config: Config) -> str:
    """Sync the org-roam DB so renamed/retitled files are reindexed."""
    form = "(progn (org-roam-db-sync) :synced)"
    proc = subprocess.run(
        ["emacsclient", "-s", config.emacs_socket, "-e", form],
        capture_output=True,
        text=True,
    )
    return (proc.stdout or proc.stderr).strip()


def run(config: Config) -> dict:
    plan = plan_assignments(config)
    to_apply = [r for r in plan if r.get("action") == "assign"]
    skipped = [r for r in plan if r.get("action") == "skip"]

    applied: list[dict] = []
    db = None
    if config.apply and to_apply:
        applied = [_apply_row(r) for r in to_apply]
        db = _reconcile_db(config)

    if config.apply:
        note = (
            f"Applied {len(applied)} assignment(s), skipped {len(skipped)}. "
            f"db-sync: {db}. Parent/child links: run repair-links next."
        )
    else:
        note = (
            f"Dry run. {len(to_apply)} note(s) would get a first folgezettel; "
            f"{len(skipped)} skipped. Re-run with --apply to execute."
        )

    payload = {
        "version": 1,
        "plan": plan,
        "apply": config.apply,
        "applied": applied,
        "skipped": skipped,
        "note": note,
    }
    config.ensure_state_dir()
    (config.state_dir / "assign-apply.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload
