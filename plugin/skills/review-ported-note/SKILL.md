---
name: review-ported-note
description: Review a freshly ported note for pandoc round-trip issues and produce a punch list the user can act on.
---

# review-ported-note

You are given two versions of the same note:

- The source file (either `.md` or `.org`).
- The converted file (the other format) with a `.port-review`
  suffix on its filename.

Compare them for these known pandoc round-trip issues:

- Fenced code blocks with a language tag that did not survive
  conversion.
- Admonitions or callouts that dropped their styling.
- Math delimiters rewritten in a way that changes rendering.
- Footnotes that lost their back-references.
- Wikilinks or `id:` links that were not translated to the target
  format's native link syntax.
- Inline tags (`#tag`) that were absorbed into text or vice versa.

Return a short JSON object with:

- `issues` — an array of `{kind, line, detail}` objects.
- `safe_to_accept` — boolean. True only when `issues` is empty or
  every issue is cosmetic.
- `summary` — one or two sentences describing the overall risk.

Do not edit the file yourself. Produce the review only.
