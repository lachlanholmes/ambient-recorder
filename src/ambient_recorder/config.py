"""Typed runtime settings. Env-overridable via AMBREC_* variables.

Constitution I / FR-010: the API may only ever bind a loopback address;
a non-loopback host is rejected at validation time, not at runtime.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

CHUNK_SECONDS = 10  # FR-002; fixed by spec Decision Log, not configurable

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class Settings(BaseModel):
    data_root: Path = Field(default=Path("data"))
    host: str = "127.0.0.1"
    port: int = Field(default=8377, ge=1, le=65535)
    min_free_disk_mb: int = Field(default=2048, ge=0)
    # feature 002 — attribution thresholds (research R4); tuned by manual accuracy test
    bleed_db: float = Field(default=6.0, ge=0)
    overlap_ratio: float = Field(default=0.6, ge=0, le=1)
    # Beam width for on-demand passes. Measured on the RTX 4070 with
    # meeting-density speech (research R2): beam 1 ≈ 6.8× real time,
    # beam 2 ≈ 3.9×, beam 5 ≈ 3.2×. NFR-002 requires ≥ 4×, so 1 is the
    # default; raise it to trade time for accuracy on a backfill you care about.
    on_demand_beam_size: int = Field(default=1, ge=1, le=8)
    # feature 003 — assistant (research R1/R2/R6)
    ollama_url: str = "http://127.0.0.1:11434"
    assistant_model: str = "llama3.2:3b"
    assistant_keep_alive_active: str = "30m"  # refreshed while a session is live
    assistant_idle_unload_s: int = Field(default=600, ge=0)  # release after stop + idle
    excerpt_budget_tokens: int = Field(default=3000, ge=200)
    summary_window_s: float = Field(default=1200.0, gt=0)

    @field_validator("ollama_url")
    @classmethod
    def _ollama_loopback_only(cls, v: str) -> str:
        from urllib.parse import urlparse

        host = urlparse(v).hostname
        if host not in _LOOPBACK_HOSTS:
            raise ValueError(
                f"ollama_url must point at a loopback host {sorted(_LOOPBACK_HOSTS)}; "
                f"got {host!r} (constitution I / FR-007: nothing leaves this machine)"
            )
        return v.rstrip("/")

    @property
    def models_dir(self) -> Path:
        return self.data_root / "models"

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, v: str) -> str:
        if v not in _LOOPBACK_HOSTS:
            raise ValueError(
                f"host must be a loopback address {sorted(_LOOPBACK_HOSTS)}; "
                f"got {v!r} (constitution I / FR-010: audio never leaves this machine)"
            )
        return v

    @property
    def sessions_root(self) -> Path:
        return self.data_root / "sessions"

    @property
    def db_path(self) -> Path:
        return self.data_root / "metadata.sqlite3"


def load_settings() -> Settings:
    """Build Settings from AMBREC_* environment variables."""
    env = {
        "data_root": os.environ.get("AMBREC_DATA_ROOT"),
        "host": os.environ.get("AMBREC_HOST"),
        "port": os.environ.get("AMBREC_PORT"),
        "min_free_disk_mb": os.environ.get("AMBREC_MIN_FREE_DISK_MB"),
        "bleed_db": os.environ.get("AMBREC_BLEED_DB"),
        "overlap_ratio": os.environ.get("AMBREC_OVERLAP_RATIO"),
        "on_demand_beam_size": os.environ.get("AMBREC_ON_DEMAND_BEAM_SIZE"),
        "ollama_url": os.environ.get("AMBREC_OLLAMA_URL"),
        "assistant_model": os.environ.get("AMBREC_ASSISTANT_MODEL"),
        "assistant_keep_alive_active": os.environ.get("AMBREC_ASSISTANT_KEEP_ALIVE"),
        "assistant_idle_unload_s": os.environ.get("AMBREC_ASSISTANT_IDLE_UNLOAD_S"),
        "excerpt_budget_tokens": os.environ.get("AMBREC_EXCERPT_BUDGET_TOKENS"),
        "summary_window_s": os.environ.get("AMBREC_SUMMARY_WINDOW_S"),
    }
    return Settings(**{k: v for k, v in env.items() if v is not None})
