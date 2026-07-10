"""Phase 7: repair links inside the ported staging files.

The port converts a note's body but cannot resolve its links, because a
link's target may be another note that is itself only just being ported.
This phase resolves them, working on the ``.port-review`` staging files
only -- the live vaults are left untouched until the user promotes.

Two directions, two link problems:

* Obsidian -> org staging (``obsidian-import/*.org.port-review``): the
  port turned every ``[[wikilink]]`` into a plain ``[[target][desc]]``
  org link. That is not a valid org-roam link -- it has no ``id:`` -- so
  it never resolves in the graph. The target text carries the folgezettel
  address, so we resolve it to the target note's ``:ID:`` and rewrite to
  ``[[id:UUID][desc]]``. ``[[file:x.md][desc]]`` links are handled too.

* org -> Obsidian staging (``org-roam-import/*.md.port-review``): the port
  turned each ``[[id:UUID][desc]]`` into a bare ``[[desc]]`` wikilink, and
  the description often lacks the address, so it will not resolve to the
  Obsidian file ``<address> <title>.md``. We resolve the target and
  rewrite to ``[[address title|desc]]`` so the wikilink lands, preserving
  the description as display text.

Resolution tries the leading folgezettel address first, then a
normalized-title fallback (used only when it is unambiguous). Anything
unresolved is reported, never guessed. The resolver spans both the live
inventory and the staging files, since a link may target a note that was
itself only just ported (its ID lives in the staging file, not the DB).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import Config
from .folgezettel import extract_from_title, canonicalize_root, parse_parent
from .matching import title_core

# org-roam (autoslip) writes every parent backlink with the generic
# description "Parent note", so the address is gone by the time the note is
# ported. Such a link is still recoverable: the parent is the folgezettel
# parent of the note that contains the link.
GENERIC_PARENT = {"parent note", "parent"}

REVIEW_SUFFIX = ".port-review"

# org plain link [[TARGET][DESC]] whose target is not already a typed link.
ORG_PLAIN_LINK_RE = re.compile(
    r"\[\[(?!id:|file:|https?:|/|\./|\.\./)([^]\n]+?)\]\[([^]\n]*?)\]\]"
)
# org file link [[file:PATH][DESC]] pointing at a (possibly renamed) note.
ORG_FILE_LINK_RE = re.compile(r"\[\[file:([^]\n]+?)\]\[([^]\n]*?)\]\]")
# an org plain link with no description: [[TARGET]]
ORG_BARE_LINK_RE = re.compile(
    r"\[\[(?!id:|file:|https?:|/|\./|\.\./)([^]\n|]+?)\]\](?!\[)"
)
# Obsidian wikilink [[TARGET]] or [[TARGET|ALIAS]]
WIKILINK_RE = re.compile(r"\[\[([^]\n|]+?)(?:\|([^]\n]*?))?\]\]")

# read a note's file-level ID and title from an org staging file
ORG_ID_RE = re.compile(r"^:ID:[ \t]+(\S+)", re.M)
ORG_TITLE_RE = re.compile(r"^#\+title:[ \t]*(.*)$", re.M | re.I)
# read the YAML title from a markdown staging file
YAML_TITLE_RE = re.compile(r"\A---\n(.*?)\n---", re.S)


def _addr_key(text: str) -> str | None:
    """Canonical folgezettel of TEXT's leading token, or None."""
    fz = extract_from_title(text)
    return canonicalize_root(fz) if fz else None


def _title_key(text: str) -> str:
    """Normalized comparison key: address and index-prefix stripped, lowered."""
    return title_core(text)


class _Resolver:
    """Maps a link target string to a note in the target vault.

    Two indices per direction: exact by folgezettel address (authoritative)
    and a fallback by normalized title (used only when unambiguous). Title
    keys that map to more than one note are dropped, so the fallback never
    guesses between collisions.
    """

    def __init__(self) -> None:
        self.by_addr: dict[str, str] = {}
        self._title_hits: dict[str, set[str]] = {}

    def add(self, address: str | None, title: str | None, value: str) -> None:
        a = canonicalize_root(address) if address else None
        if a:
            # first writer wins for an address; a later duplicate is a data
            # problem already reported elsewhere, not something to resolve here.
            self.by_addr.setdefault(a, value)
        key = _title_key(title or "")
        if key:
            self._title_hits.setdefault(key, set()).add(value)

    def resolve(self, target: str) -> str | None:
        a = _addr_key(target)
        if a and a in self.by_addr:
            return self.by_addr[a]
        key = _title_key(target)
        hits = self._title_hits.get(key)
        if hits and len(hits) == 1:
            return next(iter(hits))
        return None


def _read_org_staging(path: Path) -> tuple[str | None, str | None]:
    text = path.read_text(encoding="utf-8", errors="replace")
    mid = ORG_ID_RE.search(text)
    mt = ORG_TITLE_RE.search(text)
    return (mid.group(1) if mid else None, mt.group(1).strip() if mt else None)


def _read_md_title(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = YAML_TITLE_RE.search(text)
    if not m:
        return None
    for line in m.group(1).splitlines():
        if line.lower().startswith("title:"):
            return line.split(":", 1)[1].strip()
    return None


def _build_resolvers(config: Config, org_stage: Path, obs_stage: Path):
    """Return (to_org, to_obsidian) resolvers spanning inventory + staging.

    to_org maps a target -> an org-roam :ID: (for rewriting org links).
    to_obsidian maps a target -> an Obsidian filename stem (for wikilinks).
    """
    inv = json.loads(config.inventory_path().read_text(encoding="utf-8"))
    to_org = _Resolver()
    to_obsidian = _Resolver()

    for rec in inv["records"]:
        fz = rec.get("folgezettel")
        title = rec.get("title")
        if rec["side"] == "org-roam" and rec.get("org_roam_id"):
            to_org.add(fz, title, rec["org_roam_id"])
        elif rec["side"] == "obsidian":
            stem = Path(rec["path"]).stem
            to_obsidian.add(fz, title, stem)

    # Staging files: a link may target a note that was itself only ported.
    for p in sorted(org_stage.glob(f"*{REVIEW_SUFFIX}")):
        org_id, title = _read_org_staging(p)
        if org_id:
            to_org.add(extract_from_title(title or ""), title, org_id)
    for p in sorted(obs_stage.glob(f"*{REVIEW_SUFFIX}")):
        title = _read_md_title(p)
        if title:
            stem = p.name[: -len(REVIEW_SUFFIX)]
            if stem.endswith(".md"):
                stem = stem[:-3]
            to_obsidian.add(extract_from_title(title), title, stem)

    return to_org, to_obsidian


def _repair_org_file(path: Path, to_org: _Resolver, plan, unresolved):
    text = path.read_text(encoding="utf-8", errors="replace")
    changed = False

    def plain(m):
        nonlocal changed
        target, desc = m.group(1), m.group(2)
        tid = to_org.resolve(target)
        if tid:
            changed = True
            plan.append({"file": str(path), "old": m.group(0),
                         "new": f"[[id:{tid}][{desc}]]"})
            return f"[[id:{tid}][{desc}]]"
        unresolved.append({"file": str(path), "direction": "to-org", "target": target})
        return m.group(0)

    def file_link(m):
        nonlocal changed
        raw, desc = m.group(1), m.group(2)
        stem = Path(raw.split("::")[0]).name
        for ext in (".md", ".org"):
            if stem.endswith(ext):
                stem = stem[: -len(ext)]
        tid = to_org.resolve(stem)
        if tid:
            changed = True
            plan.append({"file": str(path), "old": m.group(0),
                         "new": f"[[id:{tid}][{desc}]]"})
            return f"[[id:{tid}][{desc}]]"
        unresolved.append({"file": str(path), "direction": "to-org", "target": stem})
        return m.group(0)

    text = ORG_FILE_LINK_RE.sub(file_link, text)
    text = ORG_PLAIN_LINK_RE.sub(plain, text)
    return text, changed


def _repair_md_file(path: Path, to_obsidian: _Resolver, plan, unresolved):
    text = path.read_text(encoding="utf-8", errors="replace")
    changed = False
    own_title = _read_md_title(path)
    own_addr = canonicalize_root(extract_from_title(own_title or "") or "") \
        if own_title else None

    def wiki(m):
        nonlocal changed
        target, alias = m.group(1), m.group(2)
        stem = to_obsidian.resolve(target)
        if stem is None and target.strip().lower() in GENERIC_PARENT and own_addr:
            parent = parse_parent(own_addr)
            pkey = canonicalize_root(parent) if parent else None
            if pkey:
                stem = to_obsidian.by_addr.get(pkey)
        if stem is None:
            unresolved.append({"file": str(path), "direction": "to-obsidian",
                               "target": target})
            return m.group(0)
        if stem == target:
            return m.group(0)  # already lands correctly
        display = alias if alias is not None else target
        new = f"[[{stem}|{display}]]"
        changed = True
        plan.append({"file": str(path), "old": m.group(0), "new": new})
        return new

    text = WIKILINK_RE.sub(wiki, text)
    return text, changed


def run(config: Config) -> dict:
    org_stage = config.org_roam_vault / "obsidian-import"
    obs_stage = config.obsidian_vault / "org-roam-import"

    plan: list[dict] = []
    unresolved: list[dict] = []
    applied = 0

    if org_stage.exists() or obs_stage.exists():
        to_org, to_obsidian = _build_resolvers(config, org_stage, obs_stage)

        for p in sorted(org_stage.glob(f"*{REVIEW_SUFFIX}")):
            new_text, changed = _repair_org_file(p, to_org, plan, unresolved)
            if changed and config.apply:
                p.write_text(new_text, encoding="utf-8")
                applied += 1
        for p in sorted(obs_stage.glob(f"*{REVIEW_SUFFIX}")):
            new_text, changed = _repair_md_file(p, to_obsidian, plan, unresolved)
            if changed and config.apply:
                p.write_text(new_text, encoding="utf-8")
                applied += 1

    files = len({r["file"] for r in plan})
    note = (
        f"{'Applied' if config.apply else 'Dry run'}: {len(plan)} link rewrites "
        f"across {files} files; {len(unresolved)} unresolved (left as-is). "
        + ("Files written." if config.apply else "Re-run with --apply to write.")
    )
    payload = {
        "version": 1,
        "plan": plan,
        "unresolved": unresolved,
        "broken_id_links": [],
        "apply": config.apply,
        "applied": applied,
        "note": note,
    }
    config.ensure_state_dir()
    (config.state_dir / "links.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return payload
