import pytest

from src.config.config import Settings

_ORCHESTRATOR_ENV_VARS = (
    "LLM_PROVIDER",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "LLM_MODEL_NAME",
    "LANGSMITH_API_KEY",
    "LANGSMITH_TRACING",
    "LANGSMITH_PROJECT",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Strip orchestrator-related variables from the process environment.

    Combined with ``_settings()`` this keeps local secrets (real API keys from
    the developer's environment or .env files) out of test assertions and logs.
    """
    for var in _ORCHESTRATOR_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _settings() -> Settings:
    """Build Settings without reading .env files."""
    return Settings(_env_file=None)


@pytest.mark.unit
class TestOrchestratorSettings:
    def test_llm_provider_default_openai(self):
        s = _settings()
        assert s.llm_provider == "openai"

    def test_openai_api_key_default_empty(self):
        s = _settings()
        assert s.openai_api_key == ""

    def test_anthropic_api_key_default_empty(self):
        s = _settings()
        assert s.anthropic_api_key == ""

    def test_llm_model_name_default(self):
        s = _settings()
        assert s.llm_model_name == "gpt-4o-mini"

    def test_langsmith_tracing_default_false(self):
        s = _settings()
        assert s.langsmith_tracing is False

    def test_langsmith_api_key_default_empty(self):
        s = _settings()
        assert s.langsmith_api_key == ""

    def test_langsmith_project_default(self):
        s = _settings()
        assert s.langsmith_project == "travel-planner"

    def test_openai_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        s = _settings()
        assert s.openai_api_key == "sk-test-key"

    def test_llm_provider_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        s = _settings()
        assert s.llm_provider == "anthropic"

    def test_langsmith_tracing_from_env(self, monkeypatch):
        monkeypatch.setenv("LANGSMITH_TRACING", "true")
        s = _settings()
        assert s.langsmith_tracing is True
