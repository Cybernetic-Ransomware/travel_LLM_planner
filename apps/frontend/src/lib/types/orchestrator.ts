import type { components } from './generated/api.js';

export type ChatMessage = components['schemas']['ChatMessage'];
export type ChatRequest = components['schemas']['ChatRequest'];
export type OrchestratorStatus = components['schemas']['OrchestratorStatusOut'];

// SSE event payloads are not described by OpenAPI (the /chat endpoint is a StreamingResponse
// with no response_model) — handwritten by necessity, not duplication of a generated contract.
export interface ToolProposal {
	tool: string;
	args: Record<string, unknown>;
}

export type SSEEvent =
	| { session_id: string }
	| { content: string }
	| { tool_proposal: ToolProposal }
	| { error: string };
