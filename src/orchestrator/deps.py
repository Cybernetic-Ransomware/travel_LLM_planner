from typing import Annotated

from fastapi import Depends, Request

from src.orchestrator.manager import OrchestratorManager


def get_orchestrator(request: Request) -> OrchestratorManager | None:
    """FastAPI dependency — returns the shared OrchestratorManager from app state.

    Returns None when the orchestrator was not initialized (missing LLM API key).
    Callers must handle the None case and return 503 if the feature is required.
    """
    return request.app.state.orchestrator


OrchestratorDep = Annotated[OrchestratorManager | None, Depends(get_orchestrator)]
