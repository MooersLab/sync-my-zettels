---
description: Rewrite cross-note links on both sides after renames and ports.
---

Run `sync-my-zettels repair-links --json`. Report any broken
`[[id:...]]` links on the org-roam side before proposing edits.
Then show the proposed wikilink rewrites on the Obsidian side.

Ask the user to confirm before rerunning with `--apply`.
