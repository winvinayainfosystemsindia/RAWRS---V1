"""Tests for the AI subsystem redesign: registry.init_ai(), resource
preflight, and GET /api/ai/status.

Goal under test: AI is an optional, pluggable capability that can never
crash the backend. All tests here run in RAWRS_AI_STUB mode except where
a test explicitly targets QwenProvider's real-path preflight logic
(which never imports torch/transformers for real — it's monkeypatched).
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _clear_ai_stub_env():
    had = os.environ.get("RAWRS_AI_STUB")
    yield
    if had is None:
        os.environ.pop("RAWRS_AI_STUB", None)
    else:
        os.environ["RAWRS_AI_STUB"] = had


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from src.api.main import app
    return TestClient(app)


# ===========================================================================
# init_ai() never raises
# ===========================================================================


class TestInitAiNeverRaises:
    def test_init_ai_with_stub_is_a_noop(self, monkeypatch):
        monkeypatch.setenv("RAWRS_AI_STUB", "1")
        from src.ai.registry import init_ai
        init_ai()  # must not raise

    def test_init_ai_swallows_unexpected_exception(self, monkeypatch):
        monkeypatch.delenv("RAWRS_AI_STUB", raising=False)
        import src.ai.registry as reg_mod

        def boom():
            raise RuntimeError("simulated catastrophic failure")

        monkeypatch.setattr(reg_mod, "_candidate_providers", boom)
        reg_mod.init_ai()  # must not raise, even though _candidate_providers blew up

    def test_init_ai_calls_start_background_load_when_present(self, monkeypatch):
        monkeypatch.delenv("RAWRS_AI_STUB", raising=False)
        import src.ai.registry as reg_mod
        from unittest.mock import MagicMock

        provider = MagicMock()
        provider.name = "MockQwen"
        monkeypatch.setattr(reg_mod, "_candidate_providers", lambda: [provider])

        reg_mod.init_ai()

        provider.start_background_load.assert_called_once()


# ===========================================================================
# QwenProvider resource preflight
# ===========================================================================


class TestResourcePreflight:
    def test_check_resources_none_when_ample_ram(self, monkeypatch):
        import src.ai.providers.qwen as qwen_mod
        import types
        import unittest.mock as mock

        fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False))
        fake_psutil = types.SimpleNamespace(
            virtual_memory=lambda: types.SimpleNamespace(available=64 * 1024**3)
        )
        with mock.patch.dict("sys.modules", {"torch": fake_torch, "psutil": fake_psutil}):
            reason = qwen_mod._check_resources()
        assert reason is None

    def test_check_resources_flags_insufficient_ram(self, monkeypatch):
        import src.ai.providers.qwen as qwen_mod
        import types
        import unittest.mock as mock

        fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False))
        fake_psutil = types.SimpleNamespace(
            virtual_memory=lambda: types.SimpleNamespace(available=1 * 1024**3)
        )
        with mock.patch.dict("sys.modules", {"torch": fake_torch, "psutil": fake_psutil}):
            reason = qwen_mod._check_resources()
        assert reason is not None
        assert "Insufficient RAM" in reason

    def test_start_background_load_marks_unavailable_without_spawning_thread(self, monkeypatch):
        """If preflight fails, from_pretrained() must never be attempted."""
        pytest.importorskip("torch")
        pytest.importorskip("transformers")
        import src.ai.providers.qwen as qwen_mod

        monkeypatch.setattr(qwen_mod, "_model", None)
        monkeypatch.setattr(qwen_mod, "_processor", None)
        monkeypatch.setattr(qwen_mod, "_load_error", None)
        monkeypatch.setattr(qwen_mod, "_loading", False)
        monkeypatch.setattr(qwen_mod, "_check_resources", lambda: "Insufficient RAM: simulated")

        called = []
        monkeypatch.setattr(
            qwen_mod.threading, "Thread",
            lambda *a, **kw: called.append(True) or pytest.fail("should not spawn a thread"),
        )

        qwen_mod.start_background_load()

        assert qwen_mod._load_error == "Insufficient RAM: simulated"
        assert not called
        caps = qwen_mod.QwenProvider().capabilities()
        assert caps.available is False
        assert caps.unavailable_reason == "Insufficient RAM: simulated"


# ===========================================================================
# GET /api/ai/status
# ===========================================================================


class TestAiStatusEndpoint:
    def test_status_available_under_stub(self, client, monkeypatch):
        monkeypatch.setenv("RAWRS_AI_STUB", "1")
        resp = client.get("/api/ai/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["provider"] == "Stub"
        assert "alt_text" in body["capabilities"]
        assert "table_analysis" in body["capabilities"]

    def test_status_never_raises_when_provider_unavailable(self, client, monkeypatch):
        monkeypatch.delenv("RAWRS_AI_STUB", raising=False)
        import src.ai.registry as reg_mod
        from unittest.mock import MagicMock

        unavail = MagicMock()
        unavail.name = "Mock"
        unavail.capabilities.return_value = MagicMock(
            available=False, unavailable_reason="no AI deps installed"
        )
        monkeypatch.setattr(reg_mod, "_candidate_providers", lambda: [unavail])

        resp = client.get("/api/ai/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
