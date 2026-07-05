<script lang="ts">
	import type { DayPlan } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';
	import StepCard from '$lib/components/optimizer/StepCard.svelte';

	let { dayPlan }: { dayPlan: DayPlan } = $props();

	const totalTravelS = $derived(
		dayPlan.steps.reduce((s, step) => s + step.travel_from_previous_s, 0)
	);
	const totalVisitMin = $derived(dayPlan.steps.reduce((s, step) => s + step.visit_duration_min, 0));

	function formatDuration(seconds: number): string {
		const min = Math.round(seconds / 60);
		if (min < 60) return `${min} min`;
		return `${Math.floor(min / 60)}h ${min % 60}m`;
	}
</script>

<div class="flex flex-col gap-2">
	<div class="flex items-center justify-between">
		<h3 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
			{m.day_label()}
			{dayPlan.day_index + 1}
			<span class="ml-1 font-normal text-zinc-500 dark:text-zinc-400">{dayPlan.date}</span>
		</h3>
		<div class="flex gap-3 text-xs text-zinc-500 dark:text-zinc-400">
			<span>{dayPlan.steps.length} {m.results_places_unit()}</span>
			<span>{formatDuration(totalTravelS)} {m.results_travel_label()}</span>
			<span>{totalVisitMin} min {m.results_visits_label()}</span>
		</div>
	</div>

	{#if dayPlan.steps.length > 0}
		<div class="flex flex-col gap-2">
			{#each dayPlan.steps as step, i (step.place_id)}
				<StepCard {step} index={i} />
			{/each}
		</div>
	{:else}
		<p
			class="rounded-md border border-dashed border-zinc-300 py-4 text-center text-xs text-zinc-400 dark:border-zinc-700"
		>
			{m.results_no_schedule()}
		</p>
	{/if}

	{#if dayPlan.skipped.length > 0}
		<div
			class="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-800 dark:bg-amber-950"
		>
			<p class="text-xs font-semibold text-amber-700 dark:text-amber-300">
				{dayPlan.skipped.length}
				{m.results_skipped_label()}
			</p>
			{#each dayPlan.skipped as s (s.place_id)}
				<p class="text-xs text-zinc-600 dark:text-zinc-400">
					{s.name ?? s.place_id}
					<span class="text-zinc-400 dark:text-zinc-500"
						>— {s.reason.replace(/_/g, ' ').toLowerCase()}</span
					>
				</p>
			{/each}
		</div>
	{/if}
</div>
