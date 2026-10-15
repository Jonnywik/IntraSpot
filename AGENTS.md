@C:\Users\mikae\.codex\RTK.md

## graphify

Canonical project knowledge lives in the Obsidian notes at `C:\Users\mikae\OneDrive\Documents\Obsidian Vault\Hermes\Projects\IntraSpot\`. The workspace copies of `Development Handoff.md` and `IDEA.md` are not the source of truth.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- Start project questions at Obsidian `IntraSpot/AI Index.md`; use its links to find the authoritative topic note. The detailed topic notes own decisions; Development Handoff is the current-stage brief; Open Questions contains unresolved decisions; Future Ideas are not commitments.
- For project questions, query `graphify-out/graph.json` first when it exists, then verify claims in the linked source notes. Graphify is a navigation aid: inferred edges are leads, not requirements. Use `graphify query "<question>"`, `graphify path "<A>" "<B>"`, and `graphify explain "<concept>"` for scoped graph views.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- The graph corpus is the canonical Obsidian folder above. When changing that corpus root, do a full `/graphify "C:\Users\mikae\OneDrive\Documents\Obsidian Vault\Hermes\Projects\IntraSpot" --directed --obsidian --obsidian-dir "C:\Users\mikae\OneDrive\Documents\Obsidian Vault\Hermes\Projects\IntraSpot\Graphify"` rebuild so old repo-copy nodes are replaced. Later note edits can use `--update --directed` with the same paths. Directed edges preserve distinctions such as “references” versus “implements.” The vault's `.graphifyignore` excludes generated Graphify exports from source input.
- After every full or incremental Graphify export, run `python scripts/style_graphify_canvas.py "C:\Users\mikae\OneDrive\Documents\Obsidian Vault\Hermes\Projects\IntraSpot\Graphify\graph.canvas" --vault-graph-settings "C:\Users\mikae\OneDrive\Documents\Obsidian Vault\.obsidian\graph.json"`. It lays out the Canvas by numbered topic zone and syncs native color groups in the main Obsidian Graph View. Do not hand-edit the generated `graph.canvas`.
- Community styling is intentionally explicit in `scripts/style_graphify_canvas.py` (`COMMUNITY_STYLE`). Assign any new Graphify community a zone, color family, and order there before formatting; unclassified labels stop the formatter so new topics cannot silently lose the hierarchy.
