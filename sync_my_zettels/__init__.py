"""sync-my-zettels: reconcile an Obsidian vault and an org-roam zettelkasten.

The top-level package is intentionally thin. The phases live in sibling
modules (inventory, roots, matching, assign, normalize, port, links, verify)
and are orchestrated through cli.main.
"""

from __future__ import annotations

__version__ = "0.1.0"
