export interface ChatMessage {
	role: 'user' | 'assistant' | 'system';
	content: string;
}

export interface ChatRequest {
	messages: ChatMessage[];
	session_id?: string | null;
	place_ids: string[];
	resume_confirmed?: boolean | null;
}

export interface ToolProposal {
	tool: string;
	args: Record<string, unknown>;
}

export type SSEEvent =
	| { session_id: string }
	| { content: string }
	| { tool_proposal: ToolProposal }
	| { error: string };

export interface OrchestratorStatus {
	ready: boolean;
	provider?: string;
	model?: string;
}
