import os
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from pymongo.asynchronous.database import AsyncDatabase

from src.config.conf_logger import setup_logger
from src.orchestrator.checkpointer import MongoCheckpointSaver
from src.orchestrator.graph import build_graph
from src.orchestrator.models import AgentState

logger = setup_logger(__name__, "orchestrator")


class OrchestratorManager:
    """Manages the LLM client, compiled LangGraph, and MongoDB checkpointer lifecycle.

    Follows the same connect/disconnect + async context manager pattern as
    GooglePlacesManager and GoogleRoutesManager.
    """

    def __init__(
        self,
        provider: str,
        api_key: str,
        model_name: str,
        langsmith_api_key: str,
        langsmith_tracing: bool,
        langsmith_project: str,
        db: AsyncDatabase | None = None,
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._model_name = model_name
        self._langsmith_api_key = langsmith_api_key
        self._langsmith_tracing = langsmith_tracing
        self._langsmith_project = langsmith_project
        self._db = db
        self._llm: BaseChatModel | None = None
        self._graph: CompiledStateGraph | None = None
        self._checkpointer: MongoCheckpointSaver | None = None

    @property
    def graph(self) -> CompiledStateGraph:
        if self._graph is None:
            raise RuntimeError("OrchestratorManager: not connected — call connect() first")
        return self._graph

    def _create_llm(self) -> BaseChatModel:
        """Instantiate the LLM based on the configured provider."""
        if self._provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(api_key=self._api_key, model=self._model_name)  # type: ignore[arg-type]
        if self._provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(api_key=self._api_key, model=self._model_name)  # type: ignore[arg-type]
        raise ValueError(f"Unsupported LLM provider: {self._provider!r}. Use 'openai' or 'anthropic'.")

    async def connect(self) -> None:
        """Create the LLM, compile the graph, and configure LangSmith tracing."""
        if self._langsmith_tracing and self._langsmith_api_key:
            os.environ["LANGSMITH_API_KEY"] = self._langsmith_api_key
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGSMITH_PROJECT"] = self._langsmith_project
            logger.info("LangSmith tracing enabled — project=%s", self._langsmith_project)

        self._llm = self._create_llm()

        if self._db is not None:
            self._checkpointer = MongoCheckpointSaver(self._db)
            self._graph = build_graph(self._llm, checkpointer=self._checkpointer)
            logger.info(
                "OrchestratorManager connected — provider=%s model=%s checkpointer=mongodb",
                self._provider,
                self._model_name,
            )
        else:
            self._graph = build_graph(self._llm)
            logger.info(
                "OrchestratorManager connected — provider=%s model=%s checkpointer=none", self._provider, self._model_name
            )

    async def disconnect(self) -> None:
        """Release graph and LLM resources."""
        self._graph = None
        self._llm = None
        self._checkpointer = None

    async def __aenter__(self) -> OrchestratorManager:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()

    async def astream(self, state: AgentState, thread_id: str | None = None) -> AsyncIterator[dict[str, Any]]:
        """Stream LangGraph events for a conversation turn.

        Yields raw astream_events dicts. The router consumes these and formats
        SSE chunks for the client.
        """
        if self._graph is None:
            raise RuntimeError("OrchestratorManager: not connected — call connect() first")

        config: RunnableConfig | None = None
        if thread_id:
            config = {"configurable": {"thread_id": thread_id}}

        async for event in self._graph.astream_events(state, config=config, version="v2"):
            yield event
