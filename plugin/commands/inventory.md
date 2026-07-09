---
description: Run phase 1 of sync-my-zettels and show the inventory summary.
---

Run the inventory phase of sync-my-zettels. Shell out to
`sync-my-zettels inventory --json` and pretty-print the counts: total
notes, notes per side, notes with a folgezettel, and notes without one.
Flag any file that could not be read.

After the run, remind the user where the JSON checkpoint lives and
suggest `/sync-zettels:roots` as the next step.
