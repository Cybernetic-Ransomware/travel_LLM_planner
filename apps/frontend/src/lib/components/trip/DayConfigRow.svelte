<script lang="ts">
	import type { DayConfig } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		config,
		index,
		canRemove,
		onchange,
		onremove
	}: {
		config: DayConfig;
		index: number;
		canRemove: boolean;
		onchange: (updated: DayConfig) => void;
		onremove: () => void;
	} = $props();

	function update(field: keyof DayConfig, value: string | number) {
		onchange({ ...config, [field]: value });
	}
</script>

<div class="flex items-center gap-2 rounded-md border border-zinc-200 bg-white px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900">
	<span class="w-14 shrink-0 text-xs font-semibold text-zinc-500 dark:text-zinc-400">{m.day_label()} {index + 1}</span>

	<input
		type="date"
		value={config.date}
		onchange={(e) => update('date', (e.target as HTMLInputElement).value)}
		class="flex-1 rounded border border-zinc-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
	/>

	<input
		type="number"
		min="0"
		max="23"
		value={config.day_start_hour}
		onchange={(e) => update('day_start_hour', Number((e.target as HTMLInputElement).value))}
		class="w-14 rounded border border-zinc-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
		title="Start hour"
	/>

	<span class="text-xs text-zinc-400">–</span>

	<input
		type="number"
		min="1"
		max="24"
		value={config.day_end_hour}
		onchange={(e) => update('day_end_hour', Number((e.target as HTMLInputElement).value))}
		class="w-14 rounded border border-zinc-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
		title="End hour"
	/>

	<button
		type="button"
		onclick={onremove}
		disabled={!canRemove}
		class="ml-auto text-zinc-400 hover:text-red-500 disabled:cursor-not-allowed disabled:opacity-30 dark:hover:text-red-400"
		aria-label="Remove day"
	>
		✕
	</button>
</div>
