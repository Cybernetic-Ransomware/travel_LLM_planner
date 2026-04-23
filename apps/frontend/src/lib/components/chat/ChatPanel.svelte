<script lang="ts">
	import { getChatContext } from '$lib/state/context.svelte.js';
	import ChatMessage from './ChatMessage.svelte';
	import ToolProposal from './ToolProposal.svelte';
	import ChatInput from './ChatInput.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import * as m from '$lib/paraglide/messages.js';

	const chat = getChatContext();

	let messagesEl: HTMLDivElement;

	$effect(() => {
		// Track message count to scroll on new messages
		const _ = chat.messages.length;
		messagesEl?.scrollTo({ top: messagesEl.scrollHeight, behavior: 'smooth' });
	});
</script>

<div class="flex flex-1 flex-col overflow-hidden">
	<div bind:this={messagesEl} class="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
		{#if chat.messages.length === 0}
			<p class="mt-8 text-center text-sm text-zinc-400">{m.chat_empty()}</p>
		{/if}

		{#each chat.messages as message (message)}
			<ChatMessage {message} />
		{/each}

		{#if chat.streaming && !chat.pendingProposal}
			<div class="flex justify-start">
				<div class="rounded-2xl rounded-bl-sm bg-white px-4 py-3 shadow-sm ring-1 ring-zinc-200">
					<Spinner size="sm" />
				</div>
			</div>
		{/if}
	</div>

	{#if chat.pendingProposal}
		<div class="border-t border-amber-200 p-4">
			<ToolProposal
				proposal={chat.pendingProposal}
				onconfirm={() => chat.confirmProposal()}
				oncancel={() => chat.cancelProposal()}
			/>
		</div>
	{/if}

	{#if chat.error}
		<div class="border-t border-red-100 bg-red-50 px-4 py-2 text-xs text-red-600">
			{chat.error}
		</div>
	{/if}

	<ChatInput onsubmit={(text) => chat.send(text)} disabled={chat.streaming} />
</div>
