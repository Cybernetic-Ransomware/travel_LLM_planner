import { streamChat, cancelPendingChatTool } from '$lib/api/orchestrator.js';
import { ApiError } from '$lib/api/client.js';
import type { ChatMessage, ToolProposal, TripUpdatedEvent } from '$lib/types/index.js';

type TripPlanType = 'SINGLE_DAY' | 'MULTI_DAY';

export class ChatState {
	messages = $state<ChatMessage[]>([]);
	sessionId = $state<string | null>(null);
	streaming = $state(false);
	pendingProposal = $state<ToolProposal | null>(null);
	error = $state<string | null>(null);
	selectedPlaceIds = $state<string[]>([]);

	tripId = $state<string | null>(null);
	tripPlanType = $state<TripPlanType | null>(null);
	onTripUpdated: ((event: TripUpdatedEvent) => void) | null = null;

	// Bumped on every context switch; each _stream captures it and drops events from a stale context
	// (aborting the fetch isn't enough — the reader may have already buffered events).
	#contextEpoch = 0;
	#streamAbort: AbortController | null = null;

	async send(content: string): Promise<void> {
		if (this.streaming) return;
		this.messages.push({ role: 'user', content });
		await this._stream(null);
	}

	async confirmProposal(): Promise<void> {
		this.pendingProposal = null;
		await this._stream(true);
	}

	async cancelProposal(): Promise<void> {
		this.pendingProposal = null;
		await this._stream(false);
	}

	setTripContext(
		tripId: string,
		planType: TripPlanType,
		onUpdated: (event: TripUpdatedEvent) => void
	): void {
		if (this.tripId === tripId) {
			this.onTripUpdated = onUpdated;
			return;
		}
		this._resetForContextSwitch();
		this.tripId = tripId;
		this.tripPlanType = planType;
		this.onTripUpdated = onUpdated;
	}

	clearTripContext(): void {
		if (this.tripId === null) return;
		this._resetForContextSwitch();
		this.tripId = null;
		this.tripPlanType = null;
		this.onTripUpdated = null;
	}

	clear(): void {
		this.#contextEpoch++;
		this.#streamAbort?.abort();
		this.#streamAbort = null;
		this.messages = [];
		this.sessionId = null;
		this.streaming = false;
		this.pendingProposal = null;
		this.error = null;
		this.tripId = null;
		this.tripPlanType = null;
		this.onTripUpdated = null;
	}

	private _resetForContextSwitch(): void {
		const oldSession = this.sessionId;
		const oldTripId = this.tripId;
		const hadPending = this.pendingProposal !== null;

		this.#contextEpoch++;
		this.#streamAbort?.abort();
		this.#streamAbort = null;
		this.streaming = false;
		this.pendingProposal = null;
		this.messages = [];
		this.error = null;
		this.sessionId = null;

		if (hadPending && oldSession) {
			cancelPendingChatTool(oldSession, oldTripId ?? undefined);
		}
	}

	private async _stream(resumeConfirmed: boolean | null): Promise<void> {
		const epoch = this.#contextEpoch;
		this.#streamAbort?.abort();
		const ac = new AbortController();
		this.#streamAbort = ac;
		this.streaming = true;
		this.error = null;
		let assistantStarted = false;

		try {
			const gen = streamChat(
				{
					messages: [...this.messages],
					session_id: this.sessionId,
					trip_id: this.tripId ?? null,
					place_ids: this.selectedPlaceIds,
					resume_confirmed: resumeConfirmed
				},
				ac.signal
			);
			for await (const event of gen) {
				if (epoch !== this.#contextEpoch) return; // stale event from a previous context
				if ('session_id' in event) {
					this.sessionId = event.session_id;
				} else if ('content' in event) {
					if (!assistantStarted) {
						this.messages.push({ role: 'assistant', content: '' });
						assistantStarted = true;
					}
					this.messages[this.messages.length - 1].content += event.content;
				} else if ('tool_proposal' in event) {
					this.pendingProposal = event.tool_proposal;
				} else if ('trip_updated' in event) {
					if (event.trip_updated.trip_id === this.tripId) {
						this.onTripUpdated?.(event.trip_updated);
					}
				} else if ('error' in event) {
					this.error = event.error;
				}
			}
		} catch (err) {
			if (epoch === this.#contextEpoch && !ac.signal.aborted) {
				this.error = err instanceof ApiError ? err.detail : 'Chat error.';
			}
		} finally {
			if (epoch === this.#contextEpoch) this.streaming = false;
		}
	}
}
