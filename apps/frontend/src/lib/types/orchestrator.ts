import type { components } from './generated/api.js';

export type ChatMessage = components['schemas']['ChatMessage'];
export type ChatRequest = components['schemas']['ChatRequest'];
export type OrchestratorStatus = components['schemas']['OrchestratorStatusOut'];

// SSE payloads aren't in OpenAPI — /chat is a StreamingResponse with no response_model.
export interface ToolProposal {
	tool: string;
	args: Record<string, unknown>;
}

export interface TripUpdatedEvent {
	trip_id: string;
	revision: number;
	plan_type: 'MULTI_DAY';
	name: string;
}

export type SSEEvent =
	| { session_id: string }
	| { content: string }
	| { tool_proposal: ToolProposal }
	| { trip_updated: TripUpdatedEvent }
	| { error: string };
