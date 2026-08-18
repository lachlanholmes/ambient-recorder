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
    }
    return Settings(**{k: v for k, v in env.items() if v is not None})
