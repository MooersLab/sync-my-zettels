---
description: Parse the Obsidian master root-node index and report the roots.
---

Run `sync-my-zettels roots --json`. Parse the output and print the
list of root addresses with their topic names, in ascending order.
Report any duplicate addresses so the user can fix the master file.

Remind the user that this list is the authoritative master; no other
phase will invent root nodes on its own.
