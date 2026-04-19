import { streamChat } from '$lib/api/orchestrator.js';
import { ApiError } from '$lib/api/client.js';
import type { ChatMessage, ToolProposal } from '$lib/types/index.js';

export class ChatState {
	messages = $state<ChatMessage[]>([]);
	sessionId = $state<string | null>(null);
	streaming = $state(false);
	pendingProposal = $state<ToolProposal | null>(null);
	error = $state<string | null>(null);
	selectedPlaceIds = $state<string[]>([]);

	async send(content: string): Promise<void> {
		if (this.streaming) return;
		this.messages.push({ role: 'user', content });
		await this._stream(null);
	}

	async confirmProposal(): Promise<void> {
		this.pendingProposal = null;
		await this._stream(true);
	}

	cancelProposal(): void {
		this.pendingProposal = null;
	}

	clear(): void {
		this.messages = [];
		this.sessionId = null;
		this.streaming = false;
		this.pendingProposal = null;
		this.error = null;
	}

	private async _stream(resumeConfirmed: boolean | null): Promise<void> {
		this.streaming = true;
		this.error = null;
		let assistantStarted = false;
		try {
			const gen = streamChat({
				messages: [...this.messages],
				session_id: this.sessionId,
				place_ids: this.selectedPlaceIds,
				resume_confirmed: resumeConfirmed
			});
			for await (const event of gen) {
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
				} else if ('error' in event) {
					this.error = event.error;
				}
			}
		} catch (err) {
			this.error = err instanceof ApiError ? err.detail : 'Chat error.';
		} finally {
			this.streaming = false;
		}
	}
}
