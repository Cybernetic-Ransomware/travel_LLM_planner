import { ApiError } from './client.js';
import { authHeaders } from '$lib/auth/token.js';
import { readSSEStream } from '$lib/utils/sse.js';
import type { ChatRequest, SSEEvent } from '$lib/types/index.js';

const CHAT_ENDPOINT = '/api/proxy/core/orchestrator/chat';

export async function* streamChat(
	request: ChatRequest,
	signal?: AbortSignal
): AsyncGenerator<SSEEvent> {
	// Combine the caller's abort (context switch) with a hard per-request timeout.
	const timeout = AbortSignal.timeout(60_000);
	const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;

	const response = await fetch(CHAT_ENDPOINT, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', ...authHeaders() },
		body: JSON.stringify(request),
		signal: combined
	});
	if (!response.ok) {
		const text = await response.text();
		throw new ApiError(response.status, text);
	}
	yield* readSSEStream(response);
}

/**
 * Fire-and-forget cancellation of a pending confirmation-gated tool call.
 *
 * The chat stream generator does not start its fetch until iterated, so abandoning
 * it never reaches the backend. This sends a real `resume_confirmed: false` POST so
 * the server strips the dangling tool call and drops the armed write scope. Failure
 * is swallowed — the server-side single-use scope + TTL are the backstop.
 */
export function cancelPendingChatTool(sessionId: string, tripId?: string): void {
	const body: ChatRequest = {
		// The resume branch ignores message content, but ChatRequest requires a non-empty list.
		messages: [{ role: 'user', content: 'cancel' }],
		session_id: sessionId,
		trip_id: tripId ?? null,
		resume_confirmed: false
	};
	void fetch(CHAT_ENDPOINT, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', ...authHeaders() },
		body: JSON.stringify(body),
		signal: AbortSignal.timeout(5_000)
	}).catch(() => {});
}
