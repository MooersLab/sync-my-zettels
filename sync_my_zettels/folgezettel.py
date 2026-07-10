"""Folgezettel parsing helpers, kept in sync with the autoslip-roam grammar.

The grammar is strict: one period after the root number (the root itself
carries a trailing period, such as 1., 7.), then alternating letters and
numbers (1.2, 1.2a, 1.2a3, 1.2a3b, ...). Legacy bare-integer titles such
as "1 Introduction" are accepted on read and canonicalized to "1.".
"""

from __future__ import annotations

import re
from typing import Optional


# A folgezettel is the LEADING token of the string and is followed by
# whitespace (or ends the string). Anchoring matters: a permissive search
# turns any number anywhere into a bogus address -- "Assembling Table 2"
# would yield "2.", "310-helix" would yield "310.", and an org-roam
# timestamp stem "20210316104407-foo" would yield "20210316104407.".
FOLGEZETTEL_RE = re.compile(
    r"\A\s*([0-9]+(?:[.][0-9]+)*(?:[a-z]+(?:[0-9]+)?)*\.?)(?=\s|\Z)"
)
ROOT_RE = re.compile(r"\A[0-9]+\.?\Z")
BARE_ROOT_RE = re.compile(r"\A[0-9]+\Z")


def is_root_address(address: Optional[str]) -> bool:
    """Return True for digits with an optional trailing period (``1`` or ``1.``)."""
    return bool(address) and bool(ROOT_RE.match(address))


def canonicalize_root(address: Optional[str]) -> Optional[str]:
    """Return ADDRESS with a trailing period if it is a bare-integer root.

    Non-root addresses are returned unchanged.
    """
    if address is None:
        return None
    if BARE_ROOT_RE.match(address):
        return address + "."
    return address


def extract_from_title(title: Optional[str]) -> Optional[str]:
    """Pull the folgezettel address off the FRONT of a note TITLE.

    The address must be the leading token and be followed by whitespace
    (or end the string). Returns the canonical form (trailing period for
    roots), or None when the title carries no folgezettel prefix.
    """
    if not title:
        return None
    match = FOLGEZETTEL_RE.match(title)
    if not match:
        return None
    return canonicalize_root(match.group(1).rstrip("."))


def parse_parent(address: Optional[str]) -> Optional[str]:
    """Return the parent of ADDRESS, or None when ADDRESS is a root.

    Mirrors autoslip-roam--parse-address: trailing letters fall off first,
    then a trailing numeric segment after a letter, then the ``.number``
    tail of a dot-number address (leaving the root's trailing period in
    place).
    """
    if not address:
        return None
    # Letters after a digit: strip all trailing letters.
    letter_tail = re.match(r"\A(.*[0-9])[a-z]+\Z", address)
    if letter_tail:
        return letter_tail.group(1)
    # Numbers after a letter: strip the trailing numeric segment.
    number_tail = re.match(r"\A(.*[a-z])[0-9]+\Z", address)
    if number_tail:
        return number_tail.group(1)
    # Dot-number after the root: strip the ``.number`` tail and leave the
    # root with its trailing period.
    dot_number = re.match(r"\A([0-9]+)\.[0-9]+\Z", address)
    if dot_number:
        return dot_number.group(1) + "."
    # A bare root has no parent.
    if is_root_address(address):
        return None
    return None
