<script lang="ts">
	import * as m from '$lib/paraglide/messages.js';
	import ChatPanel from '$lib/components/chat/ChatPanel.svelte';

	let { open = $bindable(false) }: { open?: boolean } = $props();
</script>

{#if open}
	<div
		class="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-zinc-200 bg-white shadow-xl sm:w-96 dark:border-zinc-800 dark:bg-zinc-900"
	>
		<div class="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200 px-4">
			<span class="text-sm font-semibold text-zinc-900">{m.nav_chat()}</span>
			<button
				onclick={() => (open = false)}
				class="rounded p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600"
				aria-label="Close chat"
			>
				✕
			</button>
		</div>
		<ChatPanel />
	</div>

	<button
		onclick={() => (open = false)}
		class="fixed inset-0 z-30 bg-black/10"
		aria-label="Close chat overlay"
	></button>
{/if}
