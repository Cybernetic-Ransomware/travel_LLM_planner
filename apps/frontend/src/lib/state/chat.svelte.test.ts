import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChatState } from './chat.svelte.js';
import type { SSEEvent } from '$lib/types/index.js';

vi.mock('$lib/api/orchestrator.js', () => ({
	streamChat: vi.fn()
}));

import { streamChat } from '$lib/api/orchestrator.js';

const mockStreamChat = vi.mocked(streamChat);

async function* makeStream(events: SSEEvent[]): AsyncGenerator<SSEEvent> {
	for (const event of events) yield event;
}

describe('ChatState', () => {
	let chat: ChatState;

	beforeEach(() => {
		chat = new ChatState();
		vi.clearAllMocks();
	});

	it('starts with empty state', () => {
		expect(chat.messages).toHaveLength(0);
		expect(chat.sessionId).toBeNull();
		expect(chat.streaming).toBe(false);
		expect(chat.pendingProposal).toBeNull();
		expect(chat.error).toBeNull();
	});

	it('send adds user message before streaming', async () => {
		mockStreamChat.mockReturnValue(makeStream([]));
		await chat.send('Hello');
		expect(chat.messages[0]).toEqual({ role: 'user', content: 'Hello' });
	});

	it('sets sessionId from stream event', async () => {
		mockStreamChat.mockReturnValue(makeStream([{ session_id: 'abc-123' }]));
		await chat.send('Hi');
		expect(chat.sessionId).toBe('abc-123');
	});

	it('builds assistant message from content tokens', async () => {
		mockStreamChat.mockReturnValue(
			makeStream([{ content: 'Hello' }, { content: ' world' }, { content: '!' }])
		);
		await chat.send('Hi');
		const assistant = chat.messages.find((m) => m.role === 'assistant');
		expect(assistant?.content).toBe('Hello world!');
	});

	it('sets pendingProposal from tool_proposal event', async () => {
		const proposal = { tool: 'import_list', args: { url: 'https://example.com' } };
		mockStreamChat.mockReturnValue(makeStream([{ tool_proposal: proposal }]));
		await chat.send('Import my list');
		expect(chat.pendingProposal).toEqual(proposal);
	});

	it('sets error from error event', async () => {
		mockStreamChat.mockReturnValue(makeStream([{ error: 'LLM unavailable' }]));
		await chat.send('Hi');
		expect(chat.error).toBe('LLM unavailable');
	});

	it('cancelProposal clears pendingProposal', async () => {
		const proposal = { tool: 'import_list', args: {} };
		mockStreamChat.mockReturnValue(makeStream([{ tool_proposal: proposal }]));
		await chat.send('Import');
		chat.cancelProposal();
		expect(chat.pendingProposal).toBeNull();
	});

	it('clear resets all state', async () => {
		mockStreamChat.mockReturnValue(makeStream([{ session_id: 's1' }, { content: 'Hi' }]));
		await chat.send('Hello');
		chat.clear();
		expect(chat.messages).toHaveLength(0);
		expect(chat.sessionId).toBeNull();
		expect(chat.streaming).toBe(false);
	});

	it('ignores send while streaming', async () => {
		let resolve: () => void;
		const blocker = new Promise<void>((r) => (resolve = r));
		mockStreamChat.mockReturnValue(
			// eslint-disable-next-line require-yield
			(async function* () {
				await blocker;
			})()
		);

		const first = chat.send('First');
		chat.send('Second');
		resolve!();
		await first;

		const userMessages = chat.messages.filter((m) => m.role === 'user');
		expect(userMessages).toHaveLength(1);
	});
});
