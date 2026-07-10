# sync-my-zettels

Reconcile an Obsidian vault and an org-roam zettelkasten under a shared folgezettel hierarchy.

## Status

Still under development. Not ready yet for human consumption.

## What it does

This tool keeps two zettelkastens in step:

- An Obsidian vault (markdown) that serves as the master for hierarchy and the list of root nodes.
- An org-roam vault that serves as the follower.

The two sides are reconciled in eight phases: inventory, root-node extraction, pair matching, folgezettel assignment for orphan notes, normalization of org-roam filenames and titles, porting of unpaired notes across the divide, link repair, and verification.

## Architecture

The project has two layers:

1. A Python package, `sync_my_zettels`, that does the mechanical work: parsing files, matching notes, running pandoc conversions, rewriting links, renaming files, and checkpointing every phase to JSON.
2. A Claude plugin, `sync-my-zettels`, that wraps the engine with slash commands and skills. The plugin is where human judgment lives: confirming proposals, classifying orphan notes against the master root-node list, and reviewing ported files.

## Installation

```bash
pip install -e '.[dev]'
```

Pandoc must be installed and on `PATH` for the porting phase.

## Usage

All phases default to dry-run and write their proposals under `~/.sync-my-zettels/`. Nothing on disk changes until a phase is rerun with `--apply`.

```bash
sync-my-zettels inventory
sync-my-zettels roots
sync-my-zettels match
sync-my-zettels assign
sync-my-zettels normalize --apply
sync-my-zettels port --apply
sync-my-zettels repair-links --apply
sync-my-zettels verify
```

## Configuration

Default paths are:

- Obsidian vault: `~/6544obsidian/blainesVault` (top level only)
- org-roam vault: `~/org-roam` (top level plus subfolders)
- Master root-node file: `~/6544obsidian/blainesVault/00.0 Index of indices.md`

Override any of these with command-line flags or a `~/.sync-my-zettels/config.toml` file.

## Folgezettel conventions

Addresses follow the [autoslip-roam](https://github.com/MooersLab/autoslip-roam) grammar. Root addresses carry a trailing period (`1.`, `2.`, ...). Subtopics append a period and a number (`1.2`), then alternate letters and numbers (`1.2a`, `1.2a3`, ...).

## License

GPL v3 or later. See [LICENSE](LICENSE).
