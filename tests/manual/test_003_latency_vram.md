# 003 manual: latency + VRAM co-residency (T031)

Prereq: readiness `ready`; a ~60-min session with final transcript
(the 001 soak or a slice) and a live session for step 3.

## Recorded (2026-08-25, phi4-mini, automated portion)

1. **Post-meeting Q&A (NFR-002)**: full turn (ask → completed with
   citations) in **2.8 s wall** on the accuracy session, warm model.
   **PASS** (repeat with 2 more questions + a cold-start first ask when
   running the answer key).
2. **~60-min summary (NFR-001)**: 69.3-min soak summarised end-to-end in
   **206 s = 2.96 min per 60 min — PASS** (after three live-found fixes:
   Ollama num_ctx 8192, size-split map windows, all-'none' windows are
   valid). 5-hour soak: not yet — its transcript is `interrupted_live`;
   backfill (~2.5 h GPU) then summarize: **done 2026-09-01** — backfill
   produced a completed on-demand transcript (3,573 segments, 5 h 08 m);
   summary `01M1EW0WSJ0Y0ZX4X0ASXZWB5Q` completed **without error in
   446 s (7 m 26 s)** with structured content (overview, 7 decisions,
   3 action items). **SC-002 completes-without-error clause: PASS.**
   **Known defect found by this run**: every citation resolved to seq 6
   (start 44.9 s) — the second reduce tier (first triggered by this
   5-hour run; the 69-min run fits in one tier) lets the model rewrite
   notes without faithfully preserving global `[n]` markers, and
   citation validation only checks the marker exists in the excerpt
   index, so small renumbered markers pass while pointing at the wrong
   segment. **Fixed same day** (marker-subset guard on every map/reduce
   call + 4-digit marker regex; see docs/backlog.md). Rerun on the fixed
   code (summary v2): ___
3. **Live co-residency (NFR-003/004, SC-004/005)**: live ask completed in
   **10 s wall**, watermark `live:3`, correct citation; **VRAM 4176 MiB
   with Whisper + phi4-mini resident** (4 GB headroom — PASS); session
   stopped clean (9 mic + 5 system chunks, gap-fill active, transcript
   final ≤ 30 s); STT lag 0.0 at rest (processing-watermark metric,
   fixed this session).
4. **Egress (SC-007)**: not formally observed yet — Resource Monitor
   check during the answer-key run: ___

Result (date, model, pass/fail): automated portion **PASS 2026-08-25**;
5-h summary + egress observation to complete with T030's run: ________
