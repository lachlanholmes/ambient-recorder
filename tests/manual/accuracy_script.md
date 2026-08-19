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

Scoring (fill after stop, from `GET /sessions/<id>/transcript`):

- Lines present exactly once (fuzzy match ≥ 70% words): ____ / 12
- Correct `me`/`them` attribution: ____ / 12 → ____ %  (PASS ≥ 90%)
- Bleed duplicates (a B line also appearing as `me`): ____  (PASS 0)
- Overlap-talk check: say line 12 *while* line 11 plays → both present,
  attributed correctly? ____

If bleed duplicates > 0, inspect `data/sessions/<id>` loudness per
track over that span; tune `AMBREC_BLEED_DB` (default 6) /
`AMBREC_OVERLAP_RATIO` (default 0.6) and re-run; record the chosen
values here: ______. Optional: rerun with `distil-large-v3` in
`data/models/` preferred (edit readiness POLICY) and compare scores.

Result (date, model, score): ______________________________________
