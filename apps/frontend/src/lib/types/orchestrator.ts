import type { components } from './generated/api.js';

export type ChatMessage = components['schemas']['ChatMessage'];
export type ChatRequest = components['schemas']['ChatRequest'];
export type OrchestratorStatus = components['schemas']['OrchestratorStatusOut'];

// SSE payloads aren't in OpenAPI — /chat is a StreamingResponse with no response_model.
export interface ToolProposal {
	tool: string;
	args: Record<string, unknown>;
}

export type SSEEvent =
	| { session_id: string }
	| { content: string }
	| { tool_proposal: ToolProposal }
	| { error: string };
