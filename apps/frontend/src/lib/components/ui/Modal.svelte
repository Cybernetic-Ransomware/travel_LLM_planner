<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		open = $bindable(false),
		title,
		children,
		footer
	}: {
		open?: boolean;
		title: string;
		children: Snippet;
		footer?: Snippet;
	} = $props();
</script>

{#if open}
	<div class="fixed inset-0 z-50 flex items-center justify-center p-4">
		<button
			class="absolute inset-0 bg-black/40"
			onclick={() => (open = false)}
			aria-label="Close modal"
		></button>

		<div class="relative z-10 w-full max-w-md rounded-xl border border-zinc-200 bg-white shadow-xl dark:border-zinc-700 dark:bg-zinc-900">
			<div class="flex items-center justify-between border-b border-zinc-100 px-5 py-4 dark:border-zinc-800">
				<h2 class="text-base font-semibold text-zinc-900 dark:text-zinc-100">{title}</h2>
				<button
					onclick={() => (open = false)}
					class="rounded p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
					aria-label="Close"
				>
					✕
				</button>
			</div>

			<div class="px-5 py-4">
				{@render children()}
			</div>

			{#if footer}
				<div class="flex justify-end gap-2 border-t border-zinc-100 px-5 py-3 dark:border-zinc-800">
					{@render footer()}
				</div>
			{/if}
		</div>
	</div>
{/if}
