---
description: Rewrite org-roam filenames and titles to match the master addresses.
---

Run `sync-my-zettels normalize --json` first to see the plan. Print
each proposed retitle as a line of the form:
`<old folgezettel> -> <new folgezettel>  (<file path>)`.

Ask the user to confirm the whole plan. On confirmation, rerun with
`--apply`. When the engine version that shells out to emacs is in
place, relay any errors from the emacs batch process verbatim.
