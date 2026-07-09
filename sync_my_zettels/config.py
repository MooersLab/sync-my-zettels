"""Shared paths and defaults for sync-my-zettels.

Every phase reads its inputs and writes its checkpoint JSON relative to
paths defined here. Overrides come from the command line or from a future
config file at ~/.sync-my-zettels/config.toml.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


HOME = Path.home()

DEFAULT_OBSIDIAN_VAULT = HOME / "6544obsidian" / "blainesVault"
DEFAULT_ORG_ROAM_VAULT = HOME / "org-roam"
DEFAULT_ROOT_INDEX_FILE = DEFAULT_OBSIDIAN_VAULT / "00.0 Index of indices.md"
DEFAULT_STATE_DIR = HOME / ".sync-my-zettels"


@dataclass(frozen=True)
class Config:
    """Runtime configuration, resolved once at the top of each phase."""

    obsidian_vault: Path = DEFAULT_OBSIDIAN_VAULT
    org_roam_vault: Path = DEFAULT_ORG_ROAM_VAULT
    root_index_file: Path = DEFAULT_ROOT_INDEX_FILE
    state_dir: Path = DEFAULT_STATE_DIR
    apply: bool = False

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
