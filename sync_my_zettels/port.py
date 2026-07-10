"""Phase 6: create the missing counterpart for every unpaired note.

Obsidian-only notes are converted with pandoc (markdown -> org) and written
under the org-roam vault with a canonical timestamped filename. A top-level
property drawer carrying a freshly minted ``:ID:`` is prepended so org-roam
indexes the new file as a node. The drawer MUST start on line 1: a leading
blank line makes org ignore the file-level ID entirely.

org-roam-only notes are converted (org -> gfm) and written under the Obsidian
vault with that vault's ``<address> <title>.md`` filename convention plus a
YAML frontmatter block. The org ``:ID:`` is preserved as ``org_id`` so links
can be repaired later.

The Obsidian vault is the MASTER: a ported note keeps the address the master
gives it, taken from the Obsidian *filename* (never the YAML title, which
usually omits the address).

Because pandoc round trips are lossy, and because wikilinks / ``id:`` links
are not portable, every ported file lands with a ``.port-review`` suffix
appended AFTER the extension (``foo.org.port-review``). Neither vault indexes
those, so a port can be reviewed before it goes live; dropping the suffix
promotes the note.

Link handling is deliberately conservative: links are protected from pandoc
with placeholders and restored afterwards in the target vault's syntax.
Resolving them to real targets is the ``repair-links`` phase's job -- the
target often does not exist until the whole port has run.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .config import Config
from .folgezettel import extract_from_title

YAML_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
ORG_DRAWER_RE = re.compile(r"\A:PROPERTIES:\s*\n.*?:END:\s*\n", re.S)
# Strip ONLY the leading run of '#+keyword: value' lines (and blank lines).
# A blanket `^#\+\w.*$` sweep would also delete '#+begin_src' / '#+end_src'
# anywhere in the file, silently spilling code-block contents into prose --
# which then makes pandoc's org reader choke on the leaked elisp/LaTeX/shell.
# Note the required colon: '#+begin_src python' has none, so it survives.
ORG_FRONT_KEYWORD_RE = re.compile(r"\A(?:[ \t]*#\+[a-zA-Z_]+:[^\n]*\n|[ \t]*\n)+")
TITLE_KW_RE = re.compile(r"^#\+title:\s*(.+?)\s*$", re.I | re.M)
ID_RE = re.compile(r"^:ID:\s+(\S+)", re.M)

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
MD_NOTE_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+?\.md)\)")
# A markdown note body may use either style; protect both in one pass.
MD_ANY_LINK_RE = re.compile(
    r"\[\[[^\]]+\]\]|\[[^\]]*\]\([^)]+?\.md\)"
)
ORG_ID_LINK_RE = re.compile(r"\[\[id:([0-9A-Fa-f-]+)\](?:\[([^\]]*)\])?\]")

# The address is the leading token of a title ("1.2e8 About pKa values ...").
LEADING_ADDRESS_RE = re.compile(
    r"\A\s*[0-9]+(?:[.][0-9]+)*(?:[a-z]+(?:[0-9]+)?)*\.?(?=\s)\s*"
)

REVIEW_SUFFIX = ".port-review"


# ---------------------------------------------------------------- pure helpers

def split_yaml(text: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body) for a markdown note."""
    m = YAML_RE.match(text)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, text[m.end():]


def split_org_header(text: str) -> tuple[Optional[str], Optional[str], str]:
    """Return (org id, title, body) for an org note, stripping drawer+keywords."""
    org_id = None
    m = ORG_DRAWER_RE.match(text)
    if m:
        idm = ID_RE.search(m.group(0))
        org_id = idm.group(1) if idm else None
        text = text[m.end():]
    tm = TITLE_KW_RE.search(text)
    title = tm.group(1).strip() if tm else None
    body = ORG_FRONT_KEYWORD_RE.sub("", text, count=1)
    return org_id, title, body.lstrip("\n")


def slugify(text: str, limit: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return s[:limit] or "note"


def safe_filename(text: str) -> str:
    """Sanitise a string for use as a filename component."""
    return re.sub(r"[/\\:\x00-\x1f]", "-", (text or "").strip()) or "note"


def strip_leading_address(title: str) -> str:
    """Drop a leading folgezettel from a title ('1.2e8 About pKa' -> 'About pKa')."""
    return LEADING_ADDRESS_RE.sub("", title or "").strip()


def title_with_address(title: str, address: Optional[str]) -> str:
    """Ensure the title carries the master's address exactly once.

    Obsidian stores the address in the FILENAME, so a note's YAML title
    usually omits it. Ported org notes must carry it in ``#+title:`` or
    org-roam sees no folgezettel at all.
    """
    if not address:
        return title
    core = strip_leading_address(title)
    return f"{address} {core}".strip()


# A filename component must fit the filesystem limit (255 bytes on macOS/ext4).
# Leave headroom for the '.md' extension and the '.port-review' staging suffix.
MAX_OBSIDIAN_STEM = 200


def obsidian_filename(title: str) -> str:
    """Obsidian's convention is '<address> <title>.md'; the title carries both.

    A long title (author lists, verbose literature-note titles) can exceed the
    filesystem's per-component byte limit, which aborts the write. Truncate the
    stem to fit, but keep any leading folgezettel address whole -- the address
    is load-bearing for the hierarchy; the trailing prose is not.
    """
    stem = safe_filename(title)
    if len(stem.encode("utf-8")) <= MAX_OBSIDIAN_STEM:
        return f"{stem}.md"
    match = LEADING_ADDRESS_RE.match(title or "")
    address = safe_filename(match.group(0)).strip() if match else ""
    core = safe_filename(strip_leading_address(title))
    budget = MAX_OBSIDIAN_STEM - (len(address.encode("utf-8")) + 1 if address else 0)
    core = core.encode("utf-8")[: max(budget, 1)].decode("utf-8", "ignore").strip()
    stem = f"{address} {core}".strip() if address else (core or "note")
    return f"{stem}.md"


def org_filename(timestamp: str, address: Optional[str], title: str) -> str:
    # The title may already begin with the address; do not repeat it.
    core = strip_leading_address(title) if address else title
    prefix = f"{address.replace('.', '_').rstrip('_')}_" if address else ""
    return f"{timestamp}-{prefix}{slugify(core)}.org"


def promote_headings(body: str) -> str:
    """Shift every ATX heading up one level ('## X' -> '# X').

    Applied only when the duplicate leading H1 was removed, so the ported
    note keeps a level-1 outline instead of starting at level 2.
    """
    return re.sub(r"^#(#+)(\s)", r"\1\2", body, flags=re.M)


def strip_leading_h1(body: str, title: str) -> str:
    """Drop a leading '# Heading' that merely repeats the note's title."""
    m = re.match(r"\A\s*#\s+(.+?)\s*\n", body)
    if not m:
        return body
    def norm(s):
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())
    if norm(m.group(1)) == norm(strip_leading_address(title)):
        return body[m.end():].lstrip("\n")
    return body


def protect_links(text: str, pattern: re.Pattern) -> tuple[str, list[str]]:
    """Swap links for opaque placeholders pandoc will pass through untouched."""
    stash: list[str] = []

    def sub(m):
        stash.append(m.group(0))
        return f"ZZLINK{len(stash) - 1}ZZ"

    return pattern.sub(sub, text), stash


def restore_links(text: str, stash: list[str], render) -> str:
    for i, raw in enumerate(stash):
        text = text.replace(f"ZZLINK{i}ZZ", render(raw))
    return text


def wikilink_to_org(raw: str) -> str:
    m = WIKILINK_RE.match(raw)
    if not m:
        return raw
    target, alias = m.group(1), m.group(2)
    return f"[[{target}][{alias or target}]]"


def md_note_link_to_org(raw: str) -> str:
    """'[1.2e Amino acids](1.2e%20Amino%20acids.md)' -> '[[1.2e Amino acids][...]]'."""
    m = MD_NOTE_LINK_RE.match(raw)
    if not m:
        return raw
    text, target = m.group(1), m.group(2)
    target = urllib.parse.unquote(target)
    target = re.sub(r"\.md\Z", "", target)
    return f"[[{target}][{text or target}]]"


def md_link_render(raw: str) -> str:
    """Dispatch on the markdown link style being restored."""
    return wikilink_to_org(raw) if raw.startswith("[[") else md_note_link_to_org(raw)


def org_id_link_to_wikilink(raw: str) -> str:
    m = ORG_ID_LINK_RE.match(raw)
    if not m:
        return raw
    desc = m.group(2)
    # Without the target's title we keep the description; repair-links resolves it.
    return f"[[{desc}]]" if desc else raw


# ---------------------------------------------------------------- conversion

def _convert(text: str, to: str, frm: str) -> str:
    import pypandoc

    return pypandoc.convert_text(text, to, format=frm)


def convert_or_preserve(text: str, to: str, frm: str, fence: str) -> tuple[str, Optional[str]]:
    """Convert TEXT, or -- if pandoc refuses -- preserve it verbatim.

    A small tail of notes contains raw LaTeX, unbalanced blocks or exotic
    elisp that pandoc's reader rejects. Dropping them silently is the one
    outcome we cannot accept, so the body is emitted verbatim inside a code
    fence and the failure is recorded on the note itself.
    """
    try:
        return _convert(text, to, frm), None
    except Exception as exc:  # pandoc reader error on this note only
        reason = str(exc).replace("\n", " ")[:180]
        if fence == "md":
            preserved = f"```org\n{text}\n```\n"
        else:
            preserved = f"#+begin_src markdown\n{text}\n#+end_src\n"
        return preserved, reason


def port_to_org(src: Path, dest_dir: Path, address: Optional[str]) -> dict:
    """Convert an Obsidian note to org and write it under DEST_DIR."""
    raw = src.read_text(encoding="utf-8", errors="replace")
    meta, body = split_yaml(raw)
    # The master keeps the address in the FILENAME; the YAML title usually
    # omits it. Fall back to the stem, then force the address back on.
    title = title_with_address(meta.get("title") or src.stem, address)
    dedup = strip_leading_h1(body, title)
    if dedup is not body:                 # the duplicate H1 was removed
        body = promote_headings(dedup)
    body, stash = protect_links(body, MD_ANY_LINK_RE)
    # `-auto_identifiers` stops pandoc emitting a :CUSTOM_ID: drawer per heading.
    org_body, port_error = convert_or_preserve(
        body, "org", "markdown-auto_identifiers", fence="org")
    org_body = restore_links(org_body, stash, md_link_render)

    note_id = str(uuid.uuid4()).upper()
    ts = datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y%m%d%H%M%S")
    out = dest_dir / (org_filename(ts, address, title) + REVIEW_SUFFIX)
    # The property drawer MUST begin on line 1 or org ignores the file-level ID.
    err_kw = f"#+PORT_ERROR: {port_error}\n" if port_error else ""
    out.write_text(
        f":PROPERTIES:\n:ID:       {note_id}\n:END:\n"
        f"#+title: {title}\n#+filetags: :obsidian:\n{err_kw}\n{org_body}",
        encoding="utf-8",
    )
    return {"kind": "port-to-org", "source": str(src), "dest": str(out),
            "id": note_id, "address": address, "title": title,
            "port_error": port_error}


def port_to_obsidian(src: Path, dest_dir: Path) -> dict:
    """Convert an org-roam note to markdown and write it under DEST_DIR."""
    raw = src.read_text(encoding="utf-8", errors="replace")
    org_id, title, body = split_org_header(raw)
    if not title:
        return {"kind": "port-to-obsidian", "source": str(src),
                "status": "skip", "reason": "no #+title keyword"}
    address = extract_from_title(title)
    body, stash = protect_links(body, ORG_ID_LINK_RE)
    md_body, port_error = convert_or_preserve(
        body, "gfm", "org-auto_identifiers", fence="md")
    md_body = restore_links(md_body, stash, org_id_link_to_wikilink)

    # date_imported records when the port ran, not the source note's mtime.
    stamp = date.today().isoformat()
    fm = [f"title: {title}", "source: org-roam", f"date_imported: {stamp}"]
    if org_id:
        fm.append(f"org_id: {org_id}")
    if port_error:
        fm.append(f'port_error: "{port_error}"')
    out = dest_dir / (obsidian_filename(title) + REVIEW_SUFFIX)
    out.write_text("---\n" + "\n".join(fm) + "\n---\n\n" + md_body, encoding="utf-8")
    return {"kind": "port-to-obsidian", "source": str(src), "dest": str(out),
            "org_id": org_id, "address": address, "title": title,
            "port_error": port_error}


# ---------------------------------------------------------------- phase entry

def build_plan(matches: dict) -> list[dict]:
    plan: list[dict] = []
    for rec in matches["obsidian_only"]:
        plan.append({"kind": "port-to-org", "source": rec["path"],
                     "folgezettel": rec.get("folgezettel")})
    for rec in matches["org_roam_only"]:
        plan.append({"kind": "port-to-obsidian", "source": rec["path"],
                     "folgezettel": rec.get("folgezettel")})
    return plan


def run(config: Config) -> dict:
    matches = json.loads(config.matches_path().read_text(encoding="utf-8"))
    plan = build_plan(matches)

    applied: list[dict] = []
    skipped: list[dict] = []
    if config.apply:
        org_dir = config.org_roam_vault / "obsidian-import"
        obs_dir = config.obsidian_vault / "org-roam-import"
        org_dir.mkdir(parents=True, exist_ok=True)
        obs_dir.mkdir(parents=True, exist_ok=True)
        limit = getattr(config, "limit", 0)
        if limit:
            # a pilot takes the first N of EACH direction, not the first N overall
            to_org = [r for r in plan if r["kind"] == "port-to-org"][:limit]
            to_obs = [r for r in plan if r["kind"] == "port-to-obsidian"][:limit]
            rows = to_org + to_obs
        else:
            rows = plan
        for row in rows:
            src = Path(row["source"])
            try:
                if not src.exists():
                    skipped.append({**row, "status": "skip", "reason": "source missing"})
                elif row["kind"] == "port-to-org":
                    applied.append(port_to_org(src, org_dir, row.get("folgezettel")))
                else:
                    res = port_to_obsidian(src, obs_dir)
                    (skipped if res.get("status") == "skip" else applied).append(res)
            except Exception as exc:  # one bad note must not abort the run
                skipped.append({**row, "status": "error", "reason": str(exc)[:160]})

    if config.apply:
        note = (
            f"Ported {len(applied)}, skipped {len(skipped)}. Files carry the "
            f"'{REVIEW_SUFFIX}' suffix and are NOT indexed by either vault; drop "
            "the suffix to promote. Run repair-links afterwards to resolve links."
        )
    else:
        note = (
            f"Dry run. {len(plan)} notes would be ported "
            f"({sum(1 for r in plan if r['kind']=='port-to-org')} -> org, "
            f"{sum(1 for r in plan if r['kind']=='port-to-obsidian')} -> obsidian). "
            "Re-run with --apply (use --limit N for a pilot)."
        )
    payload = {"version": 1, "plan": plan, "apply": config.apply,
               "applied": applied, "skipped": skipped, "note": note}
    config.ensure_state_dir()
    (config.state_dir / "port.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
