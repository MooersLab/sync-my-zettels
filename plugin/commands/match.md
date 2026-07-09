---
description: Pair Obsidian notes with org-roam notes by normalized title.
---

Run `sync-my-zettels match --json`. Summarize the four buckets:
matched, obsidian-only, org-roam-only, ambiguous. Show the first ten
rows of each bucket so the user can spot obvious miscategorizations.

If the ambiguous bucket is nonempty, suggest the user resolve each
ambiguous group by renaming the conflicting note titles so the
normalized-title collision goes away.
