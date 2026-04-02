import pytest

from src.config.config import Settings


@pytest.mark.unit
class TestOrchestratorSettings:
    def test_llm_provider_default_openai(self):
        s = Settings()
        assert s.llm_provider == "openai"

    def test_openai_api_key_default_empty(self):
        s = Settings()
        assert s.openai_api_key == ""

    def test_anthropic_api_key_default_empty(self):
        s = Settings()
        assert s.anthropic_api_key == ""

    def test_llm_model_name_default(self):
        s = Settings()
        assert s.llm_model_name == "gpt-4o-mini"

    def test_langsmith_tracing_default_false(self):
        s = Settings()
        assert s.langsmith_tracing is False

    def test_langsmith_api_key_default_empty(self, monkeypatch):
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
        s = Settings()
        assert s.langsmith_api_key == ""

    def test_langsmith_project_default(self, monkeypatch):
        monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
        s = Settings()
        assert s.langsmith_project == "travel-planner"

    def test_openai_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        s = Settings()
        assert s.openai_api_key == "sk-test-key"

    def test_llm_provider_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        s = Settings()
        assert s.llm_provider == "anthropic"

    def test_langsmith_tracing_from_env(self, monkeypatch):
        monkeypatch.setenv("LANGSMITH_TRACING", "true")
        s = Settings()
        assert s.langsmith_tracing is True
