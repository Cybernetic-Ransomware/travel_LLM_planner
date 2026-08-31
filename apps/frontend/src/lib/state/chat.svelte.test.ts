import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChatState } from './chat.svelte.js';
import type { SSEEvent } from '$lib/types/index.js';

vi.mock('$lib/api/orchestrator.js', () => ({
	streamChat: vi.fn(),
	cancelPendingChatTool: vi.fn()
}));

import { streamChat, cancelPendingChatTool } from '$lib/api/orchestrator.js';

const mockStreamChat = vi.mocked(streamChat);
const mockCancel = vi.mocked(cancelPendingChatTool);

async function* makeStream(events: SSEEvent[]): AsyncGenerator<SSEEvent> {
	for (const event of events) yield event;
}

function deferredStream(): {
	gen: AsyncGenerator<SSEEvent>;
	release: (events: SSEEvent[]) => void;
} {
	let release!: (events: SSEEvent[]) => void;
	const ready = new Promise<SSEEvent[]>((r) => (release = r));
	async function* gen(): AsyncGenerator<SSEEvent> {
		for (const event of await ready) yield event;
	}
	return { gen: gen(), release };
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
		expect(chat.tripId).toBeNull();
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

	it('sends trip_id in the request body once a trip context is set', async () => {
		chat.setTripContext('trip-9', 'MULTI_DAY', () => {});
		mockStreamChat.mockReturnValue(makeStream([]));
		await chat.send('pin place');
		expect(mockStreamChat).toHaveBeenLastCalledWith(
			expect.objectContaining({ trip_id: 'trip-9' }),
			expect.anything()
		);
	});

	it('cancelProposal clears pendingProposal', async () => {
		const proposal = { tool: 'import_list', args: {} };
		mockStreamChat.mockReturnValue(makeStream([{ tool_proposal: proposal }]));
		await chat.send('Import');
		mockStreamChat.mockReturnValue(makeStream([]));
		await chat.cancelProposal();
		expect(chat.pendingProposal).toBeNull();
	});

	it('cancelProposal notifies backend with resume_confirmed false', async () => {
		const proposal = { tool: 'import_list', args: {} };
		mockStreamChat.mockReturnValue(makeStream([{ tool_proposal: proposal }]));
		await chat.send('Import');
		mockStreamChat.mockReturnValue(makeStream([{ content: 'Cancelled.' }]));
		await chat.cancelProposal();
		expect(mockStreamChat).toHaveBeenLastCalledWith(
			expect.objectContaining({ resume_confirmed: false }),
			expect.anything()
		);
	});

	it('confirmProposal notifies backend with resume_confirmed true', async () => {
		const proposal = { tool: 'import_list', args: {} };
		mockStreamChat.mockReturnValue(makeStream([{ tool_proposal: proposal }]));
		await chat.send('Import');
		mockStreamChat.mockReturnValue(makeStream([{ content: 'Done.' }]));
		await chat.confirmProposal();
		expect(mockStreamChat).toHaveBeenLastCalledWith(
			expect.objectContaining({ resume_confirmed: true }),
			expect.anything()
		);
	});

	it('clear resets all state', async () => {
		mockStreamChat.mockReturnValue(makeStream([{ session_id: 's1' }, { content: 'Hi' }]));
		await chat.send('Hello');
		chat.clear();
		expect(chat.messages).toHaveLength(0);
		expect(chat.sessionId).toBeNull();
		expect(chat.streaming).toBe(false);
		expect(chat.tripId).toBeNull();
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

	describe('trip context isolation', () => {
		it('setTripContext with a new id resets messages/session and bumps context', async () => {
			mockStreamChat.mockReturnValue(makeStream([{ session_id: 's1' }, { content: 'hi' }]));
			await chat.send('Hello');
			expect(chat.sessionId).toBe('s1');

			chat.setTripContext('trip-A', 'MULTI_DAY', () => {});

			expect(chat.messages).toHaveLength(0);
			expect(chat.sessionId).toBeNull();
			expect(chat.pendingProposal).toBeNull();
			expect(chat.tripId).toBe('trip-A');
		});

		it('setTripContext with the same id only swaps the callback', async () => {
			const cb1 = vi.fn();
			const cb2 = vi.fn();
			chat.setTripContext('trip-A', 'MULTI_DAY', cb1);
			mockStreamChat.mockReturnValue(makeStream([{ session_id: 's1' }]));
			await chat.send('Hello');

			chat.setTripContext('trip-A', 'MULTI_DAY', cb2);
			expect(chat.sessionId).toBe('s1');
			expect(chat.messages.length).toBeGreaterThan(0);
		});

		it('fires a real cancel request when leaving a context with a pending proposal', async () => {
			chat.setTripContext('trip-A', 'MULTI_DAY', () => {});
			mockStreamChat.mockReturnValue(
				makeStream([
					{ session_id: 'sess-A' },
					{ tool_proposal: { tool: 'edit_multi_day_trip', args: {} } }
				])
			);
			await chat.send('pin place');
			expect(chat.pendingProposal).not.toBeNull();

			chat.setTripContext('trip-B', 'MULTI_DAY', () => {});

			expect(mockCancel).toHaveBeenCalledWith('sess-A', 'trip-A');
			expect(chat.pendingProposal).toBeNull();
		});

		it('drops buffered events from a stream that started under a previous context', async () => {
			chat.setTripContext('trip-A', 'MULTI_DAY', () => {});
			const { gen, release } = deferredStream();
			mockStreamChat.mockReturnValue(gen);
			const inflight = chat.send('do a thing');

			chat.setTripContext('trip-B', 'MULTI_DAY', () => {});
			release([{ session_id: 'late' }, { content: 'late token' }, { error: 'late error' }]);
			await inflight;

			expect(chat.sessionId).toBeNull();
			expect(chat.messages).toHaveLength(0);
			expect(chat.error).toBeNull();
		});

		it('trip_updated for a different trip does not fire the callback', async () => {
			const onUpdated = vi.fn();
			chat.setTripContext('trip-A', 'MULTI_DAY', onUpdated);
			mockStreamChat.mockReturnValue(
				makeStream([
					{
						trip_updated: { trip_id: 'trip-OTHER', revision: 2, plan_type: 'MULTI_DAY', name: 'x' }
					}
				])
			);
			await chat.send('hi');
			expect(onUpdated).not.toHaveBeenCalled();
		});

		it('trip_updated for the current trip fires the callback', async () => {
			const onUpdated = vi.fn();
			chat.setTripContext('trip-A', 'MULTI_DAY', onUpdated);
			const event = { trip_id: 'trip-A', revision: 3, plan_type: 'MULTI_DAY' as const, name: 'A' };
			mockStreamChat.mockReturnValue(makeStream([{ trip_updated: event }]));
			await chat.send('hi');
			expect(onUpdated).toHaveBeenCalledWith(event);
		});
	});
});
