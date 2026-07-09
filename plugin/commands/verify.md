---
description: Verify the reconciled state and produce a final report.
---

Run `sync-my-zettels verify --json`. Print the final counts:
matched, obsidian_only, org_roam_only, ambiguous, without_folgezettel.
If `clean` is true, congratulate the user. Otherwise, suggest the
smallest set of follow-up phases to rerun.

When the emacs-batch verification step lands, also relay the output
of `org-roam-db-sync` and any autoslip-roam validation errors.
