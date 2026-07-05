import os
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from pymongo.asynchronous.database import AsyncDatabase

from src.config.conf_logger import setup_logger
from src.gmaps import GooglePlacesManager
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
        places_manager: GooglePlacesManager | None = None,
        checkpoint_ttl_days: int = 30,
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._model_name = model_name
        self._langsmith_api_key = langsmith_api_key
        self._langsmith_tracing = langsmith_tracing
        self._langsmith_project = langsmith_project
        self._db = db
        self._places_manager = places_manager
        self._checkpoint_ttl_days = checkpoint_ttl_days
        self._llm: BaseChatModel | None = None
        self._graph: CompiledStateGraph | None = None
        self._checkpointer: MongoCheckpointSaver | None = None

    @property
    def graph(self) -> CompiledStateGraph:
        if self._graph is None:
            raise RuntimeError("OrchestratorManager: not connected — call connect() first")
        return self._graph

    @property
    def places_manager(self) -> GooglePlacesManager | None:
        """Google Places API manager, or None if not configured."""
        return self._places_manager

    @property
    def is_ready(self) -> bool:
        """Whether the orchestrator graph has been compiled and is ready to serve."""
        return self._graph is not None

    @property
    def has_checkpointer(self) -> bool:
        """Whether a checkpointer is active (conversation persistence enabled)."""
        return self._checkpointer is not None

    @property
    def provider(self) -> str:
        """LLM provider name (e.g. ``'openai'``, ``'anthropic'``)."""
        return self._provider

    @property
    def model_name(self) -> str:
        """LLM model identifier (e.g. ``'gpt-4o'``, ``'claude-sonnet-4-20250514'``)."""
        return self._model_name

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
            self._checkpointer = MongoCheckpointSaver(self._db, retention_days=self._checkpoint_ttl_days)
            self._graph = build_graph(
                self._llm,
                checkpointer=self._checkpointer,
                db=self._db,
                places_manager=self._places_manager,
            )
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
        self._places_manager = None

    async def __aenter__(self) -> OrchestratorManager:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()

    async def astream(
        self,
        state: AgentState,
        thread_id: str | None = None,
        configurable: dict | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream LangGraph events for a conversation turn.

        Yields raw astream_events dicts. The router consumes these and formats
        SSE chunks for the client.

        Args:
            state: Initial agent state for this turn.
            thread_id: Checkpointer thread ID for conversation persistence.
            configurable: Extra entries merged into ``config["configurable"]``,
                e.g. ``{"allowed_place_ids": [...]}`` for the scope guard.
        """
        if self._graph is None:
            raise RuntimeError("OrchestratorManager: not connected — call connect() first")

        configurable_dict: dict = {}
        if thread_id:
            configurable_dict["thread_id"] = thread_id
        if configurable:
            configurable_dict.update(configurable)
        config: RunnableConfig | None = {"configurable": configurable_dict} if configurable_dict else None

        async for event in self._graph.astream_events(state, config=config, version="v2"):
            yield event

    async def acancel_pending_tools(self, thread_id: str, user_message: str | None = None) -> None:
        """Cancel dangling tool calls on a checkpointed thread.

        Replaces every AIMessage whose ``tool_calls`` have no matching
        ToolMessage responses with a version that has no ``tool_calls``, so
        the conversation history stays valid for the LLM provider (OpenAI
        rejects an assistant message with ``tool_calls`` that is not followed
        by tool result messages). Applies both to threads paused at the tools
        interrupt and to threads that ended with unanswered tool_calls in
        history. The optional ``user_message`` is appended after the cleaned
        messages.

        No-op when the history has no dangling tool_calls or no checkpointer
        is configured.
        """
        if self._graph is None or self._checkpointer is None:
            return

        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        graph_state = await self._graph.aget_state(config)
        if not graph_state:
            return
        messages = (graph_state.values or {}).get("messages", [])

        answered_ids = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
        cleaned = [
            AIMessage(id=m.id, content=m.content or "")
            for m in messages
            if isinstance(m, AIMessage) and m.tool_calls and any(tc["id"] not in answered_ids for tc in m.tool_calls)
        ]
        if not cleaned:
            return

        update: dict = {"messages": cleaned}
        if user_message:
            update["messages"].append(HumanMessage(content=user_message))
        await self._graph.aupdate_state(config, update)

    async def astream_resume(
        self,
        thread_id: str,
        confirmed: bool,
        user_message: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Resume a graph that was interrupted before tool execution.

        When ``confirmed=True``, the pending tool call is executed. The
        optional ``user_message`` is appended to the conversation before
        resuming so the LLM has context for its final reply.

        When ``confirmed=False``, the pending tool call is cancelled: the
        interrupted AIMessage is replaced with a version that has no
        ``tool_calls``, and the user's rejection message is appended. The
        graph resumes normally — the LLM acknowledges the cancellation.
        """
        if self._graph is None:
            raise RuntimeError("OrchestratorManager: not connected — call connect() first")
        if self._checkpointer is None:
            raise RuntimeError("OrchestratorManager: checkpointer not configured — resume requires persistence")

        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        if not confirmed:
            await self.acancel_pending_tools(thread_id, user_message)
        elif user_message:
            await self._graph.aupdate_state(config, {"messages": [HumanMessage(content=user_message)]})

        async for event in self._graph.astream_events(None, config=config, version="v2"):
            yield event
