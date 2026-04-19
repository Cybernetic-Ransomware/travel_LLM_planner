import { describe, it, expect } from 'vitest';
import { parseSSELine, readSSEStream } from './sse.js';

describe('parseSSELine', () => {
	it('returns null for lines without data: prefix', () => {
		expect(parseSSELine('')).toBeNull();
		expect(parseSSELine('event: message')).toBeNull();
		expect(parseSSELine(': comment')).toBeNull();
	});

	it('returns null for [DONE] sentinel', () => {
		expect(parseSSELine('data: [DONE]')).toBeNull();
	});

	it('returns null for malformed JSON', () => {
		expect(parseSSELine('data: not-json')).toBeNull();
	});

	it('parses session_id event', () => {
		expect(parseSSELine('data: {"session_id":"abc-123"}')).toEqual({ session_id: 'abc-123' });
	});

	it('parses content event', () => {
		expect(parseSSELine('data: {"content":"Hello"}')).toEqual({ content: 'Hello' });
	});

	it('parses tool_proposal event', () => {
		const line = 'data: {"tool_proposal":{"tool":"get_places","args":{}}}';
		expect(parseSSELine(line)).toEqual({ tool_proposal: { tool: 'get_places', args: {} } });
	});

	it('parses error event', () => {
		expect(parseSSELine('data: {"error":"Stream interrupted"}')).toEqual({
			error: 'Stream interrupted'
		});
	});
});

describe('readSSEStream', () => {
	function makeResponse(lines: string[]): Response {
		const body = lines.join('\n') + '\n';
		return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } });
	}

	it('yields parsed events from a stream', async () => {
		const response = makeResponse([
			'data: {"session_id":"abc"}',
			'data: {"content":"Hi"}',
			'data: [DONE]'
		]);

		const events = [];
		for await (const event of readSSEStream(response)) {
			events.push(event);
		}

		expect(events).toEqual([{ session_id: 'abc' }, { content: 'Hi' }]);
	});

	it('skips blank lines and non-data lines', async () => {
		const response = makeResponse([
			'',
			': keep-alive',
			'data: {"content":"token"}',
			''
		]);

		const events = [];
		for await (const event of readSSEStream(response)) {
			events.push(event);
		}

		expect(events).toEqual([{ content: 'token' }]);
	});

	it('returns immediately for null body', async () => {
		const response = new Response(null, { status: 204 });
		const events = [];
		for await (const event of readSSEStream(response)) {
			events.push(event);
		}
		expect(events).toHaveLength(0);
	});
});
