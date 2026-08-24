<script lang="ts">
	import type { RouteStep } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		step,
		index
	}: {
		step: RouteStep;
		index: number;
	} = $props();

	function formatDuration(seconds: number): string {
		const min = Math.round(seconds / 60);
		if (min < 60) return `${min} min`;
		return `${Math.floor(min / 60)}h ${min % 60}m`;
	}
</script>

<div
	class="flex gap-3 rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900"
>
	<div
		class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white"
	>
		{index + 1}
	</div>

	<div class="min-w-0 flex-1">
		<p class="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">{step.name ?? '—'}</p>
		<div class="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-zinc-500 dark:text-zinc-400">
			<span>{step.arrival_time.slice(0, 5)} → {step.departure_time.slice(0, 5)}</span>
			<span>{step.visit_duration_min} min {m.step_visit_unit()}</span>
			{#if step.travel_from_previous_s > 0}
				<span class="text-zinc-400 dark:text-zinc-500"
					>+{formatDuration(step.travel_from_previous_s)} {m.step_travel_unit()}</span
				>
			{/if}
			{#if (step.wait_min ?? 0) > 0}
				<span class="text-zinc-400 dark:text-zinc-500"
					>{step.wait_min} min {m.step_wait_unit()}</span
				>
			{/if}
		</div>
	</div>
</div>
