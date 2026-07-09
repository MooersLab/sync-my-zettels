---
description: Create the missing counterpart for every unpaired note.
---

Run `sync-my-zettels port --json` for the plan. Show the user which
Obsidian notes will be converted to org and which org-roam notes
will be converted to markdown, grouped by direction. Note the
`.port-review` suffix the engine adds to new files.

For each newly ported note, use the `review-ported-note` skill to
open the converted file and flag pandoc round-trip issues (broken
code blocks, lost callouts, rewritten math). Collect the review
notes in a single thread so the user can address them in one pass.
