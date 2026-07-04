<script lang="ts">
	import type { ToolProposal } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		proposal,
		onconfirm,
		oncancel
	}: {
		proposal: ToolProposal;
		onconfirm: () => void;
		oncancel: () => void;
	} = $props();
</script>

<div class="rounded-lg border border-amber-200 bg-amber-50 p-4">
	<p class="text-xs font-semibold tracking-wide text-amber-700 uppercase">
		{m.chat_tool_request()}
	</p>
	<p class="mt-1 text-sm font-medium text-zinc-900">{proposal.tool}</p>
	<pre
		class="mt-2 max-h-32 overflow-auto rounded bg-white p-2 text-xs text-zinc-600 ring-1 ring-zinc-200">{JSON.stringify(
			proposal.args,
			null,
			2
		)}</pre>
	<div class="mt-3 flex gap-2">
		<button
			onclick={onconfirm}
			data-testid="proposal-confirm"
			class="rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700"
		>
			{m.chat_confirm()}
		</button>
		<button
			onclick={oncancel}
			data-testid="proposal-cancel"
			class="rounded-md bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 ring-1 ring-zinc-300 hover:bg-zinc-50"
		>
			{m.chat_cancel()}
		</button>
	</div>
</div>
