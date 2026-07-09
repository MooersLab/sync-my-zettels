---
name: classify-orphan-note
description: Classify an org-roam note without a folgezettel against the master root-node list, returning the best root address and a short justification.
---

# classify-orphan-note

You are given:

- The master root-node list, an array of `{address, topic}` entries
  drawn from the Obsidian `00.0 Index of indices.md`.
- One orphan org-roam note: its title and body text.

Return a single JSON object with these fields:

- `root_address` — the canonical folgezettel address of the best
  matching root (e.g., `"3."`).
- `root_topic` — the topic string for that root.
- `confidence` — one of `"high"`, `"medium"`, `"low"`.
- `reason` — one or two sentences grounded in the note's content
  that justify the chosen root.

If no root fits, return `null` for `root_address` and explain why in
`reason`. Do not invent a new root node. The root-node list is the
authoritative master.

Do not propose a child address; that is the engine's job. You pick
the root only.
