<script lang="ts">
	import type { OptimizeResponse, PlaceOut } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';
	import StepCard from './StepCard.svelte';
	import SkippedPlaces from './SkippedPlaces.svelte';

	let {
		result,
		places,
		onmarkmustsee,
		promotedPlaceIds
	}: {
		result: OptimizeResponse;
		places?: PlaceOut[];
		onmarkmustsee?: (placeId: string) => void | Promise<void>;
		promotedPlaceIds?: Set<string>;
	} = $props();

	const plannedIds = $derived(new Set(result.steps.map((s) => s.place_id)));
	const mustSeePlaces = $derived((places ?? []).filter((p) => p.priority === 'must_see'));
	const mustSeeKept = $derived(mustSeePlaces.filter((p) => plannedIds.has(p.id)).length);

	function formatDuration(seconds: number): string {
		const min = Math.round(seconds / 60);
		if (min < 60) return `${min} min`;
		return `${Math.floor(min / 60)}h ${min % 60}m`;
	}
</script>

<div class="flex flex-col gap-3">
	<div
		class="grid grid-cols-4 gap-2 rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900"
	>
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
			<p class="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
				{result.total_visit_time_min} min
			</p>
			<p class="text-xs text-zinc-500 dark:text-zinc-400">{m.results_visits_label()}</p>
		</div>
		<div class="text-center">
			<p class="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
				{result.total_wait_min} min
			</p>
			<p class="text-xs text-zinc-500 dark:text-zinc-400">{m.results_wait_label()}</p>
		</div>
	</div>

	<p
		data-testid="route-summary"
		class="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400"
	>
		{result.steps.length}
		{m.results_summary_planned()}
		&nbsp;·&nbsp;
		{result.skipped.length}
		{m.results_summary_skipped()}
		{#if mustSeePlaces.length > 0}
			&nbsp;·&nbsp;
			{mustSeeKept}/{mustSeePlaces.length}
			{m.results_summary_must_see_kept()}
		{/if}
	</p>

	<div class="flex flex-col gap-2">
		{#each result.steps as step, i (step.place_id)}
			<StepCard {step} index={i} />
		{/each}
	</div>

	<SkippedPlaces skipped={result.skipped} {onmarkmustsee} {promotedPlaceIds} />
</div>
