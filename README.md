# Ambient Recorder

A local-first ambient meeting recorder for Windows 11. It captures your
microphone and everything your machine plays (remote call participants) as
separable audio streams, persisted durably in 10-second chunks, controlled
through a typed local REST API.

## Privacy stance (non-negotiable)

All capture and storage happens on this machine. **Raw audio and transcripts
never leave the device** — the API refuses to bind anything but a loopback
address, there is no telemetry, and no outbound network calls exist anywhere
in the codebase. See `.specify/memory/constitution.md`, Principle I.

## Status

Feature 001 (capture sessions) — foundation, API, storage, and the full
device-free test suite are implemented. The real WASAPI capture provider is
gated: per constitution Principle IV, **gate (d)**, any task that opens real
audio devices requires explicit human approval first. Until T019 lands,
`python -m ambient_recorder` exits with a gate notice.

## Development

```bash
python -m venv .venv && source .venv/Scripts/activate
pip install -e ".[dev]"
pytest            # contract + unit + integration; never touches audio devices
ruff check src tests
```

Real-device validation lives in `tests/manual/` and runs by hand only —
never in CI. End-to-end scenarios: `specs/001-ambient-audio-capture/quickstart.md`.

## Contributor notes

- Every boundary is a typed contract (Pydantic model or Protocol). Contract
  changes land in `specs/*/contracts/` and the contract modules first, in
  their own commit, before implementations.
- Gate (d) tasks are marked **[GATE-D]** in `specs/*/tasks.md`. Do not open
  audio devices — even "just to test" — without approval.
