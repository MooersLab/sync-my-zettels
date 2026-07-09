"""Shared paths and defaults for sync-my-zettels.

Every phase reads its inputs and writes its checkpoint JSON relative to
paths defined here. Overrides come from the command line or from a future
config file at ~/.sync-my-zettels/config.toml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


HOME = Path.home()

DEFAULT_OBSIDIAN_VAULT = HOME / "6544obsidian" / "blainesVault"
DEFAULT_ORG_ROAM_VAULT = HOME / "org-roam"
DEFAULT_ROOT_INDEX_FILE = DEFAULT_OBSIDIAN_VAULT / "00.0 Index of indices.md"
DEFAULT_STATE_DIR = HOME / ".sync-my-zettels"

# The normalize apply phase drives a running Emacs daemon (autoslip-roam
# does the actual renaming). The socket name and the path to autoslip-roam.el
# are resolved here so the CLI can override them.
DEFAULT_EMACS_SOCKET = os.environ.get("EMACS_SOCKET_NAME", "fallef")
DEFAULT_AUTOSLIP_ROAM_EL = (
    HOME / "6112MooersLabGitHubLabRepos" / "autoslip-roam" / "autoslip-roam.el"
)


@dataclass(frozen=True)
class Config:
    """Runtime configuration, resolved once at the top of each phase."""

    obsidian_vault: Path = DEFAULT_OBSIDIAN_VAULT
    org_roam_vault: Path = DEFAULT_ORG_ROAM_VAULT
    root_index_file: Path = DEFAULT_ROOT_INDEX_FILE
    state_dir: Path = DEFAULT_STATE_DIR
    apply: bool = False
    emacs_socket: str = DEFAULT_EMACS_SOCKET
    autoslip_roam_el: Path = DEFAULT_AUTOSLIP_ROAM_EL

    def inventory_path(self) -> Path:
        return self.state_dir / "inventory.json"

    def roots_path(self) -> Path:
        return self.state_dir / "roots.json"

    def matches_path(self) -> Path:
        return self.state_dir / "matches.json"

    def assignments_path(self) -> Path:
        return self.state_dir / "assignments.json"

    def verify_path(self) -> Path:
        return self.state_dir / "verify.json"

    def ensure_state_dir(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
