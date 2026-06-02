import { ApiError } from './client.js';
import { authHeaders } from '$lib/auth/token.js';
import { readSSEStream } from '$lib/utils/sse.js';
import type { ChatRequest, SSEEvent } from '$lib/types/index.js';

export async function* streamChat(request: ChatRequest): AsyncGenerator<SSEEvent> {
	const response = await fetch('/api/proxy/core/orchestrator/chat', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', ...authHeaders() },
		body: JSON.stringify(request),
		signal: AbortSignal.timeout(60_000)
	});
	if (!response.ok) {
		const text = await response.text();
		throw new ApiError(response.status, text);
	}
	yield* readSSEStream(response);
}
