<script lang="ts">
	import type { SkippedPlace } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';
	import {
		skipReasonMessage,
		isLowPriorityDrop,
		isTimeWindowInfeasible,
		isNoCoordinates
	} from '$lib/utils/skippedReasons.js';

	let {
		skipped,
		onmarkmustsee,
		onenrich,
		promotedPlaceIds,
		updatingPlaceId,
		placeUpdateKind
	}: {
		skipped: SkippedPlace[];
		onmarkmustsee?: (placeId: string) => void | Promise<void>;
		onenrich?: (placeId: string) => void | Promise<void>;
		promotedPlaceIds?: Set<string>;
		updatingPlaceId?: string | null;
		placeUpdateKind?: 'priority' | 'enrichment' | null;
	} = $props();

	const hasLowPriorityDrop = $derived(skipped.some((s) => isLowPriorityDrop(s.reason)));
</script>

{#if skipped.length > 0}
	<div
		class="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950"
	>
		<p class="text-xs font-semibold text-amber-700 dark:text-amber-300">
			{skipped.length}
			{m.results_places_unit()}
			{m.results_skipped_label()}
		</p>
		<ul class="mt-1 flex flex-col gap-1.5">
			{#each skipped as s (s.place_id)}
				<li class="text-xs" data-testid="skipped-place-{s.place_id}">
					<span class="font-medium text-zinc-700 dark:text-zinc-300">{s.name ?? s.place_id}</span>
					<span class="block text-zinc-500 dark:text-zinc-400">{skipReasonMessage(s.reason)}</span>
					{#if isLowPriorityDrop(s.reason) && onmarkmustsee && !promotedPlaceIds?.has(s.place_id)}
						<button
							type="button"
							onclick={() => onmarkmustsee(s.place_id)}
							disabled={!!updatingPlaceId}
							class="mt-1 rounded border border-amber-300 px-2 py-1 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-700 dark:text-amber-200 dark:hover:bg-amber-900"
						>
							{updatingPlaceId === s.place_id && placeUpdateKind === 'priority'
								? m.optimizer_preference_updating()
								: m.skipped_action_mark_must_see()}
						</button>
					{/if}
					{#if isTimeWindowInfeasible(s.reason)}
						<a
							href="/places?focus={encodeURIComponent(s.place_id)}"
							class="mt-1 inline-block text-xs font-medium text-amber-800 underline hover:text-amber-900 dark:text-amber-200 dark:hover:text-amber-100"
						>
							{m.skipped_action_edit_hours()}
						</a>
					{/if}
					{#if isNoCoordinates(s.reason) && onenrich}
						<button
							type="button"
							onclick={() => onenrich(s.place_id)}
							disabled={!!updatingPlaceId}
							class="mt-1 rounded border border-amber-300 px-2 py-1 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-700 dark:text-amber-200 dark:hover:bg-amber-900"
						>
							{updatingPlaceId === s.place_id && placeUpdateKind === 'enrichment'
								? m.optimizer_enrich_updating()
								: m.skipped_action_enrich_location()}
						</button>
					{/if}
				</li>
			{/each}
		</ul>
		{#if hasLowPriorityDrop}
			<p class="mt-2 text-xs text-amber-700 dark:text-amber-300">
				{m.skip_tip_low_priority()}
			</p>
		{/if}
	</div>
{/if}
