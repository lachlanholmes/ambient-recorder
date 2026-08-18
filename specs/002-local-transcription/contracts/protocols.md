# Contract: Transcription Protocols

Normative code: `src/ambient_recorder/transcription/protocols.py`.
Implementations: `WhisperEngine` (real, gate c), `FakeSpeechEngine`
(tests, scripted output).

## SpeechEngine

```python
class RawSegment(BaseModel):
    start_s: float; end_s: float; text: str   # relative to the audio passed in
    avg_logprob: float | None = None

class SpeechEngine(Protocol):
    @property
    def descriptor(self) -> str:
        """e.g. 'faster-whisper medium/int8_float16/cuda' — stored on Transcript.model"""

    def transcribe(self, pcm16k_mono: bytes, *, beam_size: int = 1,
                   initial_prompt: str | None = None) -> list[RawSegment]:
        """Blocking. Transcribes one 16 kHz mono s16le buffer (a chunk plus
        rolling overlap, research R3). Raises EngineError on failure; the
        worker maps that to a failed transcript. Must be safe to call
        repeatedly from a single worker thread."""

class EngineFactory(Protocol):
    def readiness(self) -> TranscriptionReadiness: ...
    def load(self) -> SpeechEngine:
        """Applies the degradation policy (research R2) and returns the
        chosen engine; raises EngineNotReadyError with the readiness
        reason. Loads at most once per process."""
```

## Attribution (pure function contract, `transcription/attribution.py`)

```python
def attribute(mic: list[TimedSegment], system: list[TimedSegment],
              mic_energy: EnergyFn, system_energy: EnergyFn,
              cfg: AttributionConfig) -> list[AttributedSegment]:
    """Merges the two tracks' candidate segments into one chronological
    list with source me/them, applying the bleed rule (research R4).
    Deterministic; no I/O; unit-tested with synthetic inputs."""
```

## TranscriptStore

```python
class TranscriptStore(Protocol):
    def create_transcript(self, t: Transcript, job: TranscriptionJob) -> None
    def append_segment(self, transcript_id: str, seg: NewSegment) -> TranscriptSegment
        """Assigns seq (monotonic per transcript). Single writer."""
    def update_job(self, transcript_id: str, **fields) -> None
    def set_state(self, transcript_id: str, state: TranscriptState,
                  *, final: bool = False, failure_reason: str | None = None) -> None
    def current_transcript(self, session_id: str) -> Transcript | None
    def list_transcripts(self, session_id: str) -> list[TranscriptSummary]
    def get_transcript(self, transcript_id: str) -> Transcript | None
    def segments_after(self, transcript_id: str, after: int) -> list[TranscriptSegment]
    def open_jobs(self) -> list[TranscriptionJob]     # startup reconciliation input
    def next_queued(self) -> TranscriptionJob | None  # on-demand queue head
```

## Chunk observer (extension of feature 001's engine)

```python
ChunkObserver = Callable[[str, SourceKind, ChunkMeta], None]
# CaptureEngine.add_chunk_observer(cb) — invoked on the writer thread AFTER
# record_chunk commits; the callback MUST return immediately (it enqueues).
# Also: CaptureEngine.add_session_observer(cb) for started/stopped events.
```

Conformance tests: `FakeSpeechEngine`/`FakeEngineFactory` and
`WhisperEngine` (structural only in CI) satisfy the Protocols;
`SqliteTranscriptStore` satisfies `TranscriptStore`.
