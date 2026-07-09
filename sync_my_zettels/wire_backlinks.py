"""Phase 7b: wire parent/child backlinks for freshly-assigned notes.

`assign-apply` gives a note-less note its first folgezettel (title +
filename) but deliberately leaves the graph links alone. This phase adds
them: for each assigned note it inserts a parent backlink in the note and
a forward child-link in the parent, using autoslip-roam's own helpers via
an emacsclient driver (`elisp/wire-backlinks.el`).

The note list comes from `assign-apply.json` (the applied rows, whose
`new_path` reflects any rename). Both edits are deduplicated in elisp, so
the phase is safe to re-run.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import Config

ELISP_DRIVER = Path(__file__).parent / "elisp" / "wire-backlinks.el"


def paths_from_assign_apply(config: Config) -> list[str]:
    """Return the applied note paths recorded by the assign-apply phase."""
    path = config.state_dir / "assign-apply.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        r["new_path"]
        for r in data.get("applied", [])
        if r.get("status") == "applied" and r.get("new_path")
    ]


def _elisp_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _run_emacs_driver(config: Config, paths: list[str]) -> list[dict]:
    config.ensure_state_dir()
    request = config.state_dir / "wire-backlinks-request.json"
    result = config.state_dir / "wire-backlinks-result.json"
    request.write_text(json.dumps({"paths": paths}, ensure_ascii=False), encoding="utf-8")
    if result.exists():
        result.unlink()

    form = "(progn (load {} nil t) (smz-wire-backlinks {} {} {}))".format(
        _elisp_string(str(ELISP_DRIVER)),
        _elisp_string(str(request)),
        _elisp_string(str(result)),
        _elisp_string(str(config.autoslip_roam_el)),
    )
    proc = subprocess.run(
        ["emacsclient", "-s", config.emacs_socket, "-e", form],
        capture_output=True,
        text=True,
    )
    if not result.exists():
        raise RuntimeError(
            "emacs wire-backlinks driver produced no result file.\n"
            f"exit: {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    payload = json.loads(result.read_text(encoding="utf-8"))
    if "error" in payload:
        raise RuntimeError(f"emacs wire-backlinks driver failed: {payload['error']}")
    return payload["results"]


def run(config: Config) -> dict:
    paths = paths_from_assign_apply(config)

    wired: list[dict] = []
    skipped: list[dict] = []
    if config.apply and paths:
        for res in _run_emacs_driver(config, paths):
            (wired if res.get("status") == "wired" else skipped).append(res)

    if config.apply:
        note = f"Wired {len(wired)} note(s); {len(skipped)} skipped/error."
    else:
        note = (
            f"Dry run. {len(paths)} assigned note(s) would have parent/child "
            "backlinks wired. Re-run with --apply to execute."
        )

    payload = {
        "version": 1,
        "paths": paths,
        "apply": config.apply,
        "wired": wired,
        "skipped": skipped,
        "note": note,
    }
    config.ensure_state_dir()
    (config.state_dir / "wire-backlinks.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload
