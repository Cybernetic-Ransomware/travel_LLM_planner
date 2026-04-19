import type { SSEEvent } from '$lib/types/index.js';

export function parseSSELine(line: string): SSEEvent | null {
	if (!line.startsWith('data: ')) return null;
	const payload = line.slice(6).trim();
	if (payload === '[DONE]') return null;
	try {
		return JSON.parse(payload) as SSEEvent;
	} catch {
		return null;
	}
}

export async function* readSSEStream(response: Response): AsyncGenerator<SSEEvent> {
	if (!response.body) return;

	const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
	let buffer = '';

	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			buffer += value;
			const lines = buffer.split('\n');
			buffer = lines.pop() ?? '';
			for (const line of lines) {
				const event = parseSSELine(line);
				if (event !== null) yield event;
			}
		}
	} finally {
		reader.releaseLock();
	}
}
