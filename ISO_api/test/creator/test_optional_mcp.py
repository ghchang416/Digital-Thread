from unittest.mock import Mock

import pytest

from src.utils.optional_mcp import mount_optional_mcp


def test_success_mounts_adapter():
    factory = Mock()
    assert mount_optional_mcp(object(), factory) is factory.return_value
    factory.return_value.mount.assert_called_once()


def test_incompatible_optional_adapter_logs_without_disabling_http(monkeypatch, caplog):
    monkeypatch.delenv("ISO_MCP_STRICT", raising=False)
    assert mount_optional_mcp(object(), Mock(side_effect=TypeError("mismatch"))) is None
    assert "MCP is unavailable" in caplog.text


def test_strict_mode_preserves_fail_fast(monkeypatch):
    monkeypatch.setenv("ISO_MCP_STRICT", "1")
    with pytest.raises(TypeError):
        mount_optional_mcp(object(), Mock(side_effect=TypeError("mismatch")))


def test_unrelated_error_not_hidden():
    with pytest.raises(RuntimeError):
        mount_optional_mcp(object(), Mock(side_effect=RuntimeError("unrelated")))
