"""Actual Access/session integration, also runnable in the minimal reader test image."""
import pytest

from src.services.creator.els.sessions import ImportSessions
from test_els_reader import runtime, fixture_path


@pytest.mark.parametrize("name", ["synthetic.mdb", "synthetic.accdb"])
def test_real_access_session_inspection_and_cleanup(runtime, tmp_path, name):
    manager = ImportSessions(tmp_path / "sessions", reader=runtime)
    try:
        import_id, token = manager.reserve("actual-access")
        manager.append(import_id, token, fixture_path(name).read_bytes())
        manager.submit(import_id, token, name)
        manager._sessions[import_id].future.result(timeout=10)
        assert manager.status(import_id, token)["status"] == "ready"
        assert manager.operations(import_id, token)["total"] > 0
        assert not list(manager.root.rglob("source.access"))
        manager.delete(import_id, token)
        assert not list(manager.root.glob("session-*"))
    finally:
        manager.close()
