# PRD-21240 · Code review

## Round 1 · 2026-10-30 · reviewed dev/PRD-21240 @ d4a3672 (base main @ 5e9e0b7)

Verdict: changes requested

### Findings

1. [must-fix] docs/tickets/PRD-21240.md:36,118,123,128,222,545 — the file contains Chinese text (bilingual glosses: "未覆盖 Rootly", "[已假设 / assumed...]", "[不阻塞 / not blocking]" ×2, "复用与清理", a quoted Chinese sentence from mcp-track.md inside the test-case-matrix table), but `mcp-track.md` §2.4 requires `docs/tickets/PRD-XXXXX.md` to be English-only for MCP repos ("只写英文的 docs/tickets/PRD-XXXXX.md"), and the review standard in §4.3 lists "仓库里没有中文" (no Chinese anywhere in the repo) as a must-fix criterion. This is also a self-test accuracy problem: the Self-test "Gates" table (docs/tickets/PRD-21240.md:526) claims `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .` returns "No hits", but re-running that exact command on this branch returns 6 hits, all inside this same file. Verified: `src/` and `tests/` are clean (zero Chinese), so this is confined to the doc, not the shipped code — but the doc itself is going to be merged into `main` as-is, and the stated gate did not actually pass.
   Fix: replace the bilingual annotations with English-only equivalents (e.g. "[assumed, not blocking]", "[not blocking]", "not covered", "reuse and cleanup", and paraphrase the mcp-track.md quote in English), then re-run the grep and correct the Gates table to reflect the true (passing) result.

### Fixes            ← filled in by the dev leg on rework
