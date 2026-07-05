<script lang="ts">
	import type { ChatMessage } from '$lib/types/index.js';

	let { message }: { message: ChatMessage } = $props();
</script>

{#if message.role === 'user'}
	<div class="flex justify-end">
		<div
			class="max-w-xs rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2 text-sm text-white lg:max-w-md"
		>
			{message.content}
		</div>
	</div>
{:else if message.role === 'assistant'}
	<div class="flex justify-start">
		<div
			class="max-w-xs rounded-2xl rounded-bl-sm bg-white px-4 py-2 text-sm whitespace-pre-wrap text-zinc-800 shadow-sm ring-1 ring-zinc-200 lg:max-w-md"
		>
			{message.content}
		</div>
	</div>
{/if}
