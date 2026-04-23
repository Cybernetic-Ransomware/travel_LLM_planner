<script lang="ts">
	import type { OptimizeResponse } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';
	import StepCard from './StepCard.svelte';

	let { result }: { result: OptimizeResponse } = $props();

	function formatDuration(seconds: number): string {
		const min = Math.round(seconds / 60);
		if (min < 60) return `${min} min`;
		return `${Math.floor(min / 60)}h ${min % 60}m`;
	}
</script>

<div class="flex flex-col gap-3">
	<div class="grid grid-cols-3 gap-2 rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
		<div class="text-center">
			<p class="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{result.steps.length}</p>
			<p class="text-xs text-zinc-500 dark:text-zinc-400">{m.results_places_unit()}</p>
		</div>
		<div class="text-center">
			<p class="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
				{formatDuration(result.total_travel_time_s)}
			</p>
			<p class="text-xs text-zinc-500 dark:text-zinc-400">{m.results_travel_label()}</p>
		</div>
		<div class="text-center">
			<p class="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{result.total_visit_time_min} min</p>
			<p class="text-xs text-zinc-500 dark:text-zinc-400">{m.results_visits_label()}</p>
		</div>
	</div>

	<div class="flex flex-col gap-2">
		{#each result.steps as step, i (step.place_id)}
			<StepCard {step} index={i} />
		{/each}
	</div>

	{#if result.skipped.length > 0}
		<div class="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950">
			<p class="text-xs font-semibold text-amber-700 dark:text-amber-300">
				{result.skipped.length} {m.results_places_unit()} {m.results_skipped_label()}
			</p>
			<ul class="mt-1 flex flex-col gap-0.5">
				{#each result.skipped as s (s.place_id)}
					<li class="text-xs text-zinc-600 dark:text-zinc-400">
						{s.name ?? s.place_id}
						<span class="text-zinc-400 dark:text-zinc-500">— {s.reason.replace(/_/g, ' ').toLowerCase()}</span>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>
