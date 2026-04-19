<script lang="ts">
	import * as m from '$lib/paraglide/messages.js';

	let {
		onsubmit,
		disabled = false
	}: {
		onsubmit: (text: string) => void;
		disabled?: boolean;
	} = $props();

	let text = $state('');

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			submit();
		}
	}

	function submit() {
		const trimmed = text.trim();
		if (!trimmed || disabled) return;
		onsubmit(trimmed);
		text = '';
	}
</script>

<div class="flex gap-2 border-t border-zinc-200 p-4">
	<textarea
		bind:value={text}
		onkeydown={handleKeydown}
		{disabled}
		rows="2"
		placeholder={m.chat_placeholder()}
		class="flex-1 resize-none rounded-md border border-zinc-300 px-3 py-2 text-sm placeholder-zinc-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-zinc-50 disabled:text-zinc-400"
	></textarea>
	<button
		onclick={submit}
		{disabled}
		data-testid="chat-send"
		class="self-end rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
	>
		{m.chat_send()}
	</button>
</div>
