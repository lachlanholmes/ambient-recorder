# 003 manual: answer-key accuracy (T030, SC-001/SC-003)

## Procedure — one command, no second person

```bash
python tests/manual/assistant_runner.py
```

Exactly like the T038 runner: TTS plays the other participant through
your speakers ("them"); you read each `[YOU say]` line aloud and press
Enter. The runner then summarizes the session, asks the 10-question
set, and prints all the scores for the sheet below (~5 minutes total).
The embedded dialogue contains exactly:

**5 decisions**: (1) ship Thursday the 14th; (2) keep the export button
but move it; (3) pricing change goes to the board; (4) hire two
engineers next quarter; (5) drop the legacy importer.

**5 action items**: (1) me — draft pricing options by Friday;
(2) them — send updated forecast before the meeting; (3) me — book the
board slot; (4) them — write the job descriptions; (5) me — email the
importer deprecation notice by end of month.

## Scoring the summary (SC-001)

`POST /sessions/<id>/summarize`, then from `GET /sessions/<id>/summary`:

- Keyed decisions captured: ___ / 5; action items: ___ / 5 (PASS ≥ 90%
  combined, i.e. ≥ 9/10)
- Owners correct on captured action items: ___ / ___
- Statements unsupported by the transcript (read the whole summary
  against the transcript): ___  (PASS 0)

## Scoring Q&A (SC-003)

10 questions in one conversation — 7 answerable (dates, owners,
decisions above), 3 not discussed (e.g. budget figure, office move,
vacation policy):

- Answerable: correct with ≥ 1 valid citation: ___ / 7 (PASS ≥ 90% → ≥ 6.3, i.e. 7/7 or 6/7)
- Unanswerable: declined (state `declined`, no guess): ___ / 3 (PASS 3/3)

Result (date, model, scores): ______________________________________
