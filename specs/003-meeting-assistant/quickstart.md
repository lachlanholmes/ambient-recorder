# Quickstart: Meeting Assistant

Validation guide. Contracts: [contracts/rest-api.md](contracts/rest-api.md).
Run from repo root.

## Prerequisites

- Features 001+002 working; **gate (c) approved and executed**: Ollama
  installed, service running, model pulled
  (`ollama pull llama3.2:3b` or the gate-(c)-chosen model).
- `curl -s 127.0.0.1:8377/assistant/readiness` → `ready:true`.

## Scenario 1 — summary of a real meeting (US1, SC-001/SC-002)

```bash
# pick a completed session with a final transcript (e.g. the accuracy run):
curl -s -X POST 127.0.0.1:8377/sessions/<id>/summarize          # 202
curl -s 127.0.0.1:8377/sessions/<id>/summary | python -m json.tool
# expect: overview, key_points/decisions/action_items each with citations;
# action items owned me/them with any spoken deadline verbatim
# scripted accuracy: tests/manual/assistant_answer_key.md (5 decisions,
# 5 action items → ≥90% captured, zero unsupported statements)
# scale check: summarize the 5-hour soak session → completes, staged
# condensation covers the whole transcript (SC-002)
```

## Scenario 2 — post-meeting Q&A with citations (US2, SC-003)

```bash
CID=$(curl -s -X POST 127.0.0.1:8377/conversations -H 'content-type: application/json' -d '{"session_ids":["<id>"]}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST 127.0.0.1:8377/conversations/$CID/ask \
     -H 'content-type: application/json' -d '{"question":"what did they say about the certificate problem?"}'
python tests/manual/answer_tail.py $CID     # watch tokens stream; terminal status carries citations
# follow-up in the same conversation: {"question":"who said that?"}
# unanswerable: {"question":"what did we decide about the office move?"}
# expect state declined ("not discussed in this meeting"), not a guess
```

## Scenario 3 — ask during a live meeting (US3, SC-004)

```bash
curl -s -X POST 127.0.0.1:8377/sessions -d '{"title":"live-assist"}' -H 'content-type: application/json'
# talk + play speech for ~2 minutes, then create a conversation and ask
# about something said ~1 min ago; watch tokens in answer_tail.py
# expect: first token ≤ 15 s, correct cited answer, watermark live:<seq>
# ask about the last ~10 seconds → answer includes the lag caveat
# verify zero chunk loss + STT lag in bound while answering (logs)
```

## Scenario 4 — honest failure and layering (US4, SC-006)

```bash
# stop the Ollama service, then:
curl -s 127.0.0.1:8377/assistant/readiness      # not_ready + remedy
curl -s -X POST 127.0.0.1:8377/sessions/<id>/summarize   # 503 assistant_not_ready
# recording/transcription continue to work throughout; restart service → ready
```

## Scenario 5 — no egress (SC-007)

During Scenarios 1–3, `netstat`/Resource Monitor shows no non-loopback
connections from the recorder or Ollama processes.
