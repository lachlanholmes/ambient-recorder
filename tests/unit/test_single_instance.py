"""The port claim is the single-instance lock: a second recorder must die
BEFORE its reconciliation can touch the shared database (2026-08-20 bug)."""

from __future__ import annotations

import pytest

from ambient_recorder.__main__ import claim_port
from ambient_recorder.config import Settings


def _free_port_settings(tmp_path) -> Settings:
    import socket

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return Settings(data_root=tmp_path, port=port)


def test_second_claim_exits_before_any_db_work(tmp_path):
    settings = _free_port_settings(tmp_path)
    first = claim_port(settings)
    try:
        with pytest.raises(SystemExit) as e:
            claim_port(settings)
        assert "already listening" in str(e.value)
        # The guard must not have created the database (it never got that far).
        assert not settings.db_path.exists()
    finally:
        first.close()
