<script lang="ts">
	import type { DayPlan } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		days,
		activeDayIndex = $bindable(0)
	}: {
		days: DayPlan[];
		activeDayIndex?: number;
	} = $props();
</script>

<div
	class="flex gap-1 overflow-x-auto rounded-lg border border-zinc-200 bg-white p-1 dark:border-zinc-800 dark:bg-zinc-900"
>
	{#each days as day, i (day.day_index)}
		<button
			type="button"
			onclick={() => (activeDayIndex = i)}
			data-testid="day-tab-{i}"
			class="shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition-colors {i ===
			activeDayIndex
				? 'bg-blue-600 text-white'
				: 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'}"
		>
			{m.day_label()}
			{day.day_index + 1}
			<span class="ml-1 text-[10px] opacity-70">{day.date}</span>
		</button>
	{/each}
</div>
