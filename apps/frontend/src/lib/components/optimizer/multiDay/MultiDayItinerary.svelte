<script lang="ts">
	import type { MultiDayResponse } from '$lib/types/index.js';
	import DayTabs from './DayTabs.svelte';
	import DayItineraryCard from './DayItineraryCard.svelte';
	import { skipReasonMessage } from '$lib/utils/skippedReasons.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		response,
		activeDayIndex = $bindable(0)
	}: {
		response: MultiDayResponse;
		activeDayIndex?: number;
	} = $props();

	const activeDay = $derived(response.days[activeDayIndex] ?? null);
</script>

<div class="flex flex-col gap-3">
	<DayTabs days={response.days} bind:activeDayIndex />

	{#if activeDay}
		<DayItineraryCard day={activeDay} />
	{/if}

	{#if response.unassigned.length > 0}
		<div
			class="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950"
		>
			<p class="text-xs font-semibold text-amber-700 dark:text-amber-300">
				{response.unassigned.length}
				{m.results_places_unit()}
				{m.multiday_unassigned_label()}
			</p>
			<ul class="mt-1 flex flex-col gap-1">
				{#each response.unassigned as u (u.place_id)}
					<li class="text-xs text-zinc-600 dark:text-zinc-400">
						<span class="font-medium">{u.name ?? u.place_id}</span> — {skipReasonMessage(u.reason)}
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>
