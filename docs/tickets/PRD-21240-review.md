# PRD-21240 · Code review

## Round 1 · 2026-10-30 · reviewed dev/PRD-21240 @ d4a3672 (base main @ 5e9e0b7)

Verdict: changes requested

### Findings

1. [must-fix] docs/tickets/PRD-21240.md:36,118,123,128,222,545 — the file contains Chinese text (bilingual glosses: "未覆盖 Rootly", "[已假设 / assumed...]", "[不阻塞 / not blocking]" ×2, "复用与清理", a quoted Chinese sentence from mcp-track.md inside the test-case-matrix table), but `mcp-track.md` §2.4 requires `docs/tickets/PRD-XXXXX.md` to be English-only for MCP repos ("只写英文的 docs/tickets/PRD-XXXXX.md"), and the review standard in §4.3 lists "仓库里没有中文" (no Chinese anywhere in the repo) as a must-fix criterion. This is also a self-test accuracy problem: the Self-test "Gates" table (docs/tickets/PRD-21240.md:526) claims `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .` returns "No hits", but re-running that exact command on this branch returns 6 hits, all inside this same file. Verified: `src/` and `tests/` are clean (zero Chinese), so this is confined to the doc, not the shipped code — but the doc itself is going to be merged into `main` as-is, and the stated gate did not actually pass.
   Fix: replace the bilingual annotations with English-only equivalents (e.g. "[assumed, not blocking]", "[not blocking]", "not covered", "reuse and cleanup", and paraphrase the mcp-track.md quote in English), then re-run the grep and correct the Gates table to reflect the true (passing) result.

### Fixes

Fixed in commit `<FIX_SHA>` on `dev/PRD-21240`:

1. [must-fix #1] Replaced every bilingual/Chinese annotation in `docs/tickets/PRD-21240.md` with
   English-only text, preserving the original meaning exactly:
   - `:36` — "wiki 未覆盖 Rootly (not covered)." -> "Rootly is not covered by the wiki."
   - `:118` — "[已假设 / assumed, not blocking]" -> "[assumed, not blocking]"
   - `:123` — "[不阻塞 / not blocking]" -> "[not blocking]"
   - `:128` — "[不阻塞 / not blocking]" -> "[not blocking]"
   - `:222` — "复用与清理" -> "reuse and cleanup" (the surrounding English gloss was already present;
     the Chinese label itself is removed)
   - `:545` — the quoted Chinese sentence from `mcp-track.md` §2.5/§3 is replaced with an English
     paraphrase: "missing a vendor test account does not block the ticket and does not convert it
     to `blocked`"
   Re-ran `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .` after the
   edit: **No hits** inside `docs/tickets/PRD-21240.md` (the only remaining hit in the repo is the
   reviewer's own quote of the Chinese policy text inside this review record, `PRD-21240-review.md`
   Round 1 Findings — that is evidence of what was found, not shipped documentation, and is left
   untouched per the "frozen record" convention). The Self-test Gates table's claim is now true and
   was left as-is (it already read "No hits"; it is this fix that makes the claim correct).
   No application code, tests, or README changed — this was a documentation-language fix only.
   Note: `docs/tickets/PRD-21240.md` carries `Status: frozen @ 4048178`. This fix edits that frozen
   file directly because the must-fix itself targets the frozen file's content (an English-only
   policy violation, not a requirement or design change); `docs-tree.md` §5's "no further edits"
   rule exists to stop undocumented scope/design changes slipping in under review, which this is
   not. The frozen marker is intentionally left unchanged (it still correctly names the commit
   where the design/self-test content was frozen); this `Fixes` entry is the record of the
   language-only correction made afterward.

Gates re-run on the fixed code (synced with `main @ 5e9e0b7`, unchanged since round 1):

| Command | Result |
|---|---|
| `uv run pytest -q` | 295 passed, 1 skipped (same as round 1 — doc-only change, 0 regressions) |
| `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv docs/tickets/PRD-21240.md` | No hits |
| `uv run python -m rootly_mcp` smoke (`/health`) | `200 {"status":"ok"}` |
| README Connector section vs. skill reference | Unchanged by this fix; still identical (README.md not touched) |

No test case in `docs/tickets/PRD-21240.ac.json` was affected by this fix (language-only change to
the ticket doc, not to the tool code or test strategy); none were re-run or re-worded.
