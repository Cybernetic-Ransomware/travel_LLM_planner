import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.manager import OrchestratorManager


def _make_manager(**kwargs) -> OrchestratorManager:
    defaults = {
        "provider": "openai",
        "api_key": "test-openai-key",
        "model_name": "gpt-4o-mini",
        "langsmith_api_key": "",
        "langsmith_tracing": False,
        "langsmith_project": "test-project",
    }
    defaults.update(kwargs)
    return OrchestratorManager(**defaults)


@pytest.mark.unit
class TestOrchestratorManagerInit:
    def test_creates_instance_with_openai_provider(self):
        manager = _make_manager(provider="openai", api_key="sk-test")
        assert manager is not None

    def test_creates_instance_with_anthropic_provider(self):
        manager = _make_manager(provider="anthropic", api_key="sk-ant-test")
        assert manager is not None

    def test_graph_raises_before_connect(self):
        manager = _make_manager()
        with pytest.raises(RuntimeError, match="not connected"):
            _ = manager.graph


@pytest.mark.unit
class TestOrchestratorManagerLLMFactory:
    def test_creates_openai_llm(self):
        from langchain_openai import ChatOpenAI

        manager = _make_manager(provider="openai", api_key="sk-test")
        llm = manager._create_llm()
        assert isinstance(llm, ChatOpenAI)

    def test_creates_anthropic_llm(self):
        from langchain_anthropic import ChatAnthropic

        manager = _make_manager(provider="anthropic", api_key="sk-ant-test")
        llm = manager._create_llm()
        assert isinstance(llm, ChatAnthropic)

    def test_unknown_provider_raises(self):
        manager = _make_manager(provider="unknown", api_key="key")
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            manager._create_llm()


@pytest.mark.unit
class TestOrchestratorManagerLifecycle:
    async def test_connect_compiles_graph(self):
        manager = _make_manager()
        with patch("src.orchestrator.manager.build_graph") as mock_build:
            mock_build.return_value = MagicMock()
            with patch.object(manager, "_create_llm", return_value=MagicMock()):
                await manager.connect()
        assert manager._graph is not None
        await manager.disconnect()

    async def test_disconnect_clears_graph(self):
        manager = _make_manager()
        with patch("src.orchestrator.manager.build_graph") as mock_build:
            mock_build.return_value = MagicMock()
            with patch.object(manager, "_create_llm", return_value=MagicMock()):
                await manager.connect()
        await manager.disconnect()
        assert manager._graph is None

    async def test_context_manager_protocol(self):
        manager = _make_manager()
        with patch("src.orchestrator.manager.build_graph") as mock_build:
            mock_build.return_value = MagicMock()
            with patch.object(manager, "_create_llm", return_value=MagicMock()):
                async with manager as m:
                    assert m is manager
                    assert m._graph is not None
        assert manager._graph is None

    async def test_langsmith_env_vars_set_when_tracing_enabled(self, monkeypatch):
        manager = _make_manager(
            langsmith_api_key="ls-key",
            langsmith_tracing=True,
            langsmith_project="my-project",
        )
        with patch("src.orchestrator.manager.build_graph", return_value=MagicMock()):
            with patch.object(manager, "_create_llm", return_value=MagicMock()):
                await manager.connect()

        assert os.environ.get("LANGSMITH_API_KEY") == "ls-key"
        assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
        assert os.environ.get("LANGSMITH_PROJECT") == "my-project"
        await manager.disconnect()
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
        monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
        monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)

    async def test_langsmith_env_vars_not_set_when_tracing_disabled(self, monkeypatch):
        monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
        manager = _make_manager(langsmith_tracing=False)
        with patch("src.orchestrator.manager.build_graph", return_value=MagicMock()):
            with patch.object(manager, "_create_llm", return_value=MagicMock()):
                await manager.connect()

        assert os.environ.get("LANGCHAIN_TRACING_V2") is None
        await manager.disconnect()


@pytest.mark.unit
class TestOrchestratorManagerAstream:
    async def test_astream_yields_events(self):
        manager = _make_manager()

        async def _fake_events(*args, **kwargs):
            yield {"event": "on_chat_model_stream", "data": {"chunk": "Hello"}}
            yield {"event": "on_chain_end", "data": {"output": "Hello"}}

        mock_graph = MagicMock()
        mock_graph.astream_events = _fake_events
        manager._graph = mock_graph

        events = [e async for e in manager.astream({"messages": [], "place_context": [], "session_id": "s1"})]
        assert len(events) == 2

    async def test_astream_raises_when_not_connected(self):
        manager = _make_manager()
        with pytest.raises(RuntimeError, match="not connected"):
            async for _ in manager.astream({"messages": [], "place_context": [], "session_id": "s1"}):
                pass
