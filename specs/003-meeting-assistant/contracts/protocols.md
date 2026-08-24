# Contract: Assistant Protocols

Normative code: `src/ambient_recorder/assistant/protocols.py`.
Implementations: `OllamaEngine` (real, gate c), `FakeAssistantEngine`
(tests, scripted token streams).

## AssistantEngine

```python
class GenerationChunk(BaseModel):
    text: str            # token(s) as produced
    done: bool = False

class AssistantEngine(Protocol):
    @property
    def descriptor(self) -> str:
        """e.g. 'ollama/llama3.2:3b' — stored on Summary.model / turn provenance"""

    def generate(self, prompt: str, *, system: str | None = None,
                 max_tokens: int = 1024) -> Iterator[GenerationChunk]:
        """Blocking generator; yields chunks as the model produces them.
        Raises EngineError on runtime failure; the worker maps it to a
        failed task/turn. Cancellation = the caller stops iterating
        (the engine must terminate the underlying request)."""

class AssistantEngineFactory(Protocol):
    def readiness(self) -> AssistantReadiness: ...
    def load(self) -> AssistantEngine:
        """Applies the residency/degradation policy (research R2/R6);
        raises EngineNotReadyError with the readiness reason."""
    def release(self) -> None:
        """Between-meetings unload (keep_alive=0); idempotent."""
```

## Pure logic contracts (unit-tested without any model)

```python
# retrieval.py
def select_excerpts(question: str, history: list[Turn],
                    segments: list[TranscriptSegment],
                    budget_tokens: int, live: bool) -> list[Excerpt]:
    """Lexical scoring (question+history overlap, recency-weighted when
    live), packed into numbered Excerpt blocks within budget."""

# grounding.py
def validate_citations(answer: str, excerpts: list[Excerpt]
                       ) -> tuple[str, list[Citation], GroundingVerdict]:
    """Extract [n] markers, map to excerpt segments, drop invalid ones;
    verdict: grounded | declined (exact decline phrase) | ungrounded."""

# summarize.py windowing
def windows(segments: list[TranscriptSegment], window_s: float = 1200.0
            ) -> list[list[TranscriptSegment]]
```

## AssistantStore

```python
class AssistantStore(Protocol):
    def create_summary(self, s: Summary, task: AssistantTask) -> None
    def complete_summary(self, summary_id: str, content: SummaryContent) -> None
    def create_conversation(self, c: Conversation) -> None
    def create_turn(self, t: ConversationTurn, task: AssistantTask) -> ConversationTurn  # assigns seq
    def append_answer_text(self, turn_id: str, text: str) -> None
    def finish_turn(self, turn_id: str, state: TurnState,
                    citations: list[Citation], watermark: str) -> None
    def update_task(self, task_id: str, **fields) -> None
    def current_summary(self, session_id: str) -> Summary | None
    def list_summaries(self, session_id: str) -> list[SummarySummary]
    def get_conversation(self, cid: str) -> ConversationDetail | None
    def list_conversations(self, session_id: str) -> list[ConversationSummary]
    def open_tasks(self) -> list[AssistantTask]      # reconciliation input
    def next_queued(self) -> AssistantTask | None    # priority order
```

Conformance: fakes + `SqliteAssistantStore` satisfy the Protocols;
`OllamaEngine` structural-only in CI (no runtime call).
