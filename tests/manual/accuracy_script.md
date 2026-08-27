# 002 manual: scripted attribution accuracy (T038, SC-001)

Two-sided script with deliberate bleed. "A" lines are spoken by you at
the laptop; "B" lines are played through the speakers (TTS or a
recording) loud enough to be audible on the mic.

| # | Side | Line |
|---|------|------|
| 1 | B | Good morning, shall we start with the roadmap? |
| 2 | A | Yes, let's begin with the mobile release. |
| 3 | B | The certificate problem pushed it by a week. |
| 4 | A | I saw that, do we have a new date? |
| 5 | B | Thursday the fourteenth, pending QA sign-off. |
| 6 | A | Okay. Second item is the dashboard feedback. |
| 7 | B | Customers love the new filters, very positive. |
| 8 | A | Great, any complaints at all? |
| 9 | B | Only the export button, it is hard to find. |
| 10 | A | Noted. Third, the pricing decision. |
| 11 | B | We need it before the end of the month. |
| 12 | A | Agreed, I will draft options by Friday. |

Scoring (fill after stop; `tests/manual/accuracy_runner.py` automates
the whole procedure including this scoring):

- Lines present exactly once (fuzzy match ≥ 70% words): **12 / 12**
- Correct `me`/`them` attribution: **12 / 12 → 100%**  (PASS ≥ 90%)
- Bleed duplicates (a B line also appearing as `me`): **0**  (PASS 0)
- Overlap-talk check: exercised via the runner's optional step; not
  separately scored (main-table result already includes any overlap
  segments — 16 segments total for 12 lines).

Per-line token coverage from the run: expected side 86–100%, bleed side
0–38% — the acoustic leak is measurable but well clear of the 70%
presence threshold, so no duplicates. `AMBREC_BLEED_DB=6` /
`AMBREC_OVERLAP_RATIO=0.6` defaults confirmed; no tuning needed.

Result history:

- **2026-08-23, medium/int8_float16/cuda: 100% attribution, 0 bleed —
  PASS** (SC-001; session 01M0REHP9HQRTN28H442DGF9RY).
- **2026-08-27 (session 01M12ACZ98V9QB6R9WKQ6AWM61): REGRESSION — 6/12,
  6 bleed duplicates.** Cause: feature 003's model pre-warm at session
  start contends with Whisper's cold start; the system track backlogs
  past the 30 s energy window, and the 08-25 expired-window fix emitted
  the unjudgeable mic copies unconditionally. Fixed same day: energy
  window widened to 300 s (must exceed worst-case STT backlog) and the
  expired path now applies the text-twin test (mic side only) before
  emitting. **Re-run pending to confirm PASS.**
