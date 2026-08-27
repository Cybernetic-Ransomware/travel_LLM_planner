<script lang="ts">
	import type { PlaceOut } from '$lib/types/index.js';
	import type { AccommodationDraft } from './accommodationDraft.js';
	import { emptyAccommodationDraft, hasNoStayOverlaps } from './accommodationDraft.js';
	import AccommodationRow from './AccommodationRow.svelte';
	import * as m from '$lib/paraglide/messages.js';

	let {
		accommodations,
		places,
		tripStart,
		tripEnd,
		disabled = false,
		onchange
	}: {
		accommodations: AccommodationDraft[];
		places: PlaceOut[];
		tripStart: string;
		tripEnd: string;
		disabled?: boolean;
		onchange: (next: AccommodationDraft[]) => void;
	} = $props();

	const overlapsFree = $derived(hasNoStayOverlaps(accommodations));

	function addRow() {
		onchange([...accommodations, emptyAccommodationDraft(crypto.randomUUID(), tripStart)]);
	}

	function updateRow(index: number, next: AccommodationDraft) {
		onchange(accommodations.map((d, i) => (i === index ? next : d)));
	}

	function removeRow(index: number) {
		onchange(accommodations.filter((_, i) => i !== index));
	}

	// Dates are never clamped to [tripStart, tripEnd] — extending beyond it is legitimate (ADR-15).
	function extendsBeyondRange(draft: AccommodationDraft): boolean {
		return draft.check_in_date < tripStart || draft.check_out_date > tripEnd;
	}
</script>

<div class="flex flex-col gap-2">
	<div class="flex items-center justify-between">
		<span class="text-xs font-medium text-zinc-700 dark:text-zinc-300"
			>{m.multiday_accommodations_label()}</span
		>
		<button
			type="button"
			onclick={addRow}
			{disabled}
			data-testid="add-accommodation"
			class="text-xs text-blue-600 hover:underline"
		>
			{m.multiday_accommodation_add()}
		</button>
	</div>

	{#each accommodations as draft, i (draft.localKey)}
		<AccommodationRow
			{draft}
			{places}
			{disabled}
			outOfRangeNote={extendsBeyondRange(draft)}
			onchange={(next) => updateRow(i, next)}
			onremove={() => removeRow(i)}
		/>
	{/each}

	{#if !overlapsFree}
		<p class="text-xs text-red-600 dark:text-red-400">{m.multiday_accommodation_overlap_error()}</p>
	{/if}
</div>
