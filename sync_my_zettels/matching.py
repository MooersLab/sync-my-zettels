"""Phase 3: pair Obsidian notes with org-roam notes.

Matches by normalized title first, then by folgezettel address as a
tie-breaker. Produces three buckets in ``matches.json``::

    matched        - both sides have a note for this normalized title
    obsidian_only  - master has it, follower does not (port to org-roam)
    org_roam_only  - follower has it, master does not (port to Obsidian,
                     and maybe also assign a folgezettel)
    ambiguous      - more than one note matched under one normalized key;
                     requires human review

The matching logic is intentionally simple in this first cut. Later
passes can bolt on content-hash fallback and a fuzzy title scorer.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .config import Config

LEADING_ADDRESS_RE = re.compile(
    r"\A\s*[0-9]+(?:[.][0-9]+)*(?:[a-z]+(?:[0-9]+)?)*\.?(?=\s)\s*"
)
_STOP = {"of", "the", "a", "an", "and", "for", "to", "in", "on", "my"}
# org-roam names its structure notes "index of X" / "subindex of X"; the
# Obsidian master just calls the same node "X". Left in place, that prefix
# inflates the word set and makes an identical root look like a collision.
INDEX_PREFIX_RE = re.compile(
    r"\A(?:sub)*index\s+(?:of\s+)?", re.I
)


def title_core(title: str | None) -> str:
    """Lowercase title, leading folgezettel and any index-prefix removed."""
    core = LEADING_ADDRESS_RE.sub("", (title or "").strip()).lower()
    return INDEX_PREFIX_RE.sub("", core).strip()


def _words(core: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", core) if w not in _STOP}


def same_note(a_title: str | None, b_title: str | None) -> bool:
    """Do two notes sharing an address describe the SAME note?

    The two vaults word the same node differently -- Obsidian's
    "105. Lectures" is org-roam's "105. index of Lectures". Treating those
    as a collision would move a note that never needed moving. Containment
    or a strong word overlap means same note; anything else is a genuine
    conflict (Obsidian "1.2 Protein structure" vs org-roam "1.2 subindex of
    cryocrystallography").
    """
    a, b = title_core(a_title), title_core(b_title)
    if not a or not b:
        return False
    sa, sb = re.sub(r"[^a-z0-9]", "", a), re.sub(r"[^a-z0-9]", "", b)
    if len(min(sa, sb, key=len)) >= 4 and (sa in sb or sb in sa):
        return True
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= 0.6


def load_pair_overrides(config: Config) -> set[str]:
    """Addresses a human has ruled to be the SAME node in both vaults.

    Some pairs are beyond any heuristic -- Obsidian's "114. My Biographies"
    is org-roam's "114. index of BHMM biographies". Rather than loosen the
    similarity threshold (which would silently swallow real conflicts), the
    decision is recorded explicitly and auditably here.
    """
    path = config.state_dir / "pair-overrides.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data.get("same_node_addresses", []))


def run(config: Config) -> dict:
    overrides = load_pair_overrides(config)
    inv_path = config.inventory_path()
    if not inv_path.exists():
        raise FileNotFoundError(
            f"Inventory not found at {inv_path}. Run the inventory phase first."
        )
    inventory = json.loads(inv_path.read_text(encoding="utf-8"))

    by_key_obsidian: dict[str, list[dict]] = defaultdict(list)
    by_key_org: dict[str, list[dict]] = defaultdict(list)
    for record in inventory["records"]:
        key = record["normalized_title"]
        if record["side"] == "obsidian":
            by_key_obsidian[key].append(record)
        else:
            by_key_org[key].append(record)

    matched: list[dict] = []
    obsidian_only: list[dict] = []
    org_roam_only: list[dict] = []
    ambiguous: list[dict] = []

    all_keys = set(by_key_obsidian) | set(by_key_org)
    for key in sorted(all_keys):
        left = by_key_obsidian.get(key, [])
        right = by_key_org.get(key, [])
        if not key:
            # Empty normalized title is never a safe match.
            ambiguous.append({"key": key, "obsidian": left, "org_roam": right})
            continue
        if len(left) > 1 or len(right) > 1:
            ambiguous.append({"key": key, "obsidian": left, "org_roam": right})
            continue
        if left and right:
            matched.append({"key": key, "obsidian": left[0], "org_roam": right[0],
                            "matched_by": "title"})
        elif left:
            obsidian_only.append(left[0])
        elif right:
            org_roam_only.append(right[0])

    # ---- second pass: pair the leftovers by folgezettel address -------------
    # Two notes at the same address are either the same node worded differently
    # (pair them) or a genuine conflict (a collision that must be resolved
    # before either side is ported).
    collisions: list[dict] = []
    obs_by_addr = defaultdict(list)
    org_by_addr = defaultdict(list)
    for r in obsidian_only:
        if r.get("folgezettel"):
            obs_by_addr[r["folgezettel"]].append(r)
    for r in org_roam_only:
        if r.get("folgezettel"):
            org_by_addr[r["folgezettel"]].append(r)

    paired_obs, paired_org = set(), set()
    for addr in sorted(set(obs_by_addr) & set(org_by_addr)):
        left, right = obs_by_addr[addr], org_by_addr[addr]
        if len(left) != 1 or len(right) != 1:
            ambiguous.append({"key": addr, "obsidian": left, "org_roam": right})
            continue
        o, g = left[0], right[0]
        if addr in overrides:
            matched.append({"key": addr, "obsidian": o, "org_roam": g,
                            "matched_by": "manual-override"})
        elif same_note(o.get("title"), g.get("title")):
            matched.append({"key": addr, "obsidian": o, "org_roam": g,
                            "matched_by": "address"})
        else:
            collisions.append({"address": addr, "obsidian": o, "org_roam": g})
        paired_obs.add(o["path"])
        paired_org.add(g["path"])

    # Notes that paired (or collided) on address are no longer "only" on a side.
    # Keeping collisions out of the port buckets means port can never write a
    # note whose address still means two different things.
    obsidian_only = [r for r in obsidian_only if r["path"] not in paired_obs]
    org_roam_only = [r for r in org_roam_only if r["path"] not in paired_org]

    payload = {
        "version": 1,
        "collisions": collisions,
        "matched": matched,
        "obsidian_only": obsidian_only,
        "org_roam_only": org_roam_only,
        "ambiguous": ambiguous,
    }
    config.ensure_state_dir()
    config.matches_path().write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload
