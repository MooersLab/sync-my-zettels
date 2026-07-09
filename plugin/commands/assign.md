---
description: Propose folgezettel addresses for org-roam notes without one.
---

Run `sync-my-zettels assign --json`. For each proposal, show the
org-roam note's title, the candidate root topic, and the suggested
address. For any row where the engine could not find a root, use the
`classify-orphan-note` skill to ask the LLM to pick the best root
given the note body and the master root-node list.

Walk the user through the list, asking for a yes/no (or override) on
each row. Append the confirmed rows to the `confirmed` array in
`~/.sync-my-zettels/assignments.json` as you go.
