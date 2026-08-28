<script lang="ts">
	import type {
		DayConfig,
		DaySlot,
		PlaceOut,
		TransferBlock,
		TransportModeNoTransit
	} from '$lib/types/index.js';
	import type { MultiDayEditableState } from './buildMultiDayRequest.js';
	import type { AccommodationDraft } from './accommodationDraft.js';
	import { hasIncompleteAccommodation } from './buildMultiDayRequest.js';
	import { hasNoStayOverlaps } from './accommodationDraft.js';
	import { isDayConfigValid } from './dayConfig.js';
	import { reconcileEditableState } from './dayRangeReconciliation.js';
	import { allTransfersValid } from './transferValidation.js';
	import { MAX_MULTIDAY_PLACES } from './placeDaySlots.js';
	import DayRangeEditor from './DayRangeEditor.svelte';
	import PlaceDayMatrix from './PlaceDayMatrix.svelte';
	import AccommodationEditor from './AccommodationEditor.svelte';
	import TransferEditor from './TransferEditor.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import * as m from '$lib/paraglide/messages.js';

	let {
		state,
		places,
		loading = false,
		hasLoadError = false,
		onchange,
		onsubmit
	}: {
		state: MultiDayEditableState;
		places: PlaceOut[];
		loading?: boolean;
		hasLoadError?: boolean;
		onchange: (next: MultiDayEditableState) => void;
		onsubmit: () => void;
	} = $props();

	const tripStart = $derived(state.days[0]?.date ?? '');
	const tripEnd = $derived(state.days.at(-1)?.date ?? '');
	const dayDates = $derived(state.days.map((d) => d.date));

	const transportOptions = [
		{ value: 'WALK', label: m.optimizer_walk() },
		{ value: 'DRIVE', label: m.optimizer_drive() },
		{ value: 'BICYCLE', label: m.optimizer_bicycle() }
	];

	const allDaysValid = $derived(state.days.every(isDayConfigValid));
	const canSubmit = $derived(
		!loading &&
			allDaysValid &&
			state.placeSelections.size >= 2 &&
			state.placeSelections.size <= MAX_MULTIDAY_PLACES &&
			!hasIncompleteAccommodation(state) &&
			hasNoStayOverlaps(state.accommodations) &&
			allTransfersValid(state.transfers)
	);

	// Every mutation funnels through here so day-range/accommodation changes always reconcile orphaned state.
	function propagate(next: MultiDayEditableState) {
		onchange(reconcileEditableState(next));
	}
	function updateDays(days: DayConfig[]) {
		propagate({ ...state, days });
	}
	function updatePlaceSelections(placeSelections: Map<string, DaySlot[]>) {
		propagate({ ...state, placeSelections });
	}
	function updateAccommodations(accommodations: AccommodationDraft[]) {
		propagate({ ...state, accommodations });
	}
	function updateTransfers(transfers: Map<string, TransferBlock>) {
		propagate({ ...state, transfers });
	}
	function updateTransportMode(mode: string) {
		propagate({ ...state, transportMode: mode as TransportModeNoTransit });
	}

	function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (!canSubmit) return;
		onsubmit();
	}
</script>

<form
	onsubmit={handleSubmit}
	class="flex flex-col gap-4 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
>
	<DayRangeEditor days={state.days} disabled={loading} onchange={updateDays} />

	{#if hasLoadError}
		<p class="text-xs text-zinc-400 dark:text-zinc-500">{m.optimizer_places_load_error()}</p>
	{:else}
		<PlaceDayMatrix
			{places}
			numDays={state.days.length}
			placeSelections={state.placeSelections}
			disabled={loading}
			onchange={updatePlaceSelections}
		/>
	{/if}

	<AccommodationEditor
		accommodations={state.accommodations}
		{places}
		{tripStart}
		{tripEnd}
		disabled={loading}
		onchange={updateAccommodations}
	/>

	<TransferEditor
		transfers={state.transfers}
		accommodations={state.accommodations}
		{dayDates}
		disabled={loading}
		onchange={updateTransfers}
	/>

	<div class="flex flex-col gap-1">
		<label for="multiday-transport" class="text-xs font-medium text-zinc-700 dark:text-zinc-300">
			{m.optimizer_transport()}
		</label>
		<select
			id="multiday-transport"
			value={state.transportMode}
			disabled={loading}
			onchange={(e) => updateTransportMode(e.currentTarget.value)}
			class="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
		>
			{#each transportOptions as option (option.value)}
				<option value={option.value}>{option.label}</option>
			{/each}
		</select>
	</div>

	<button
		type="submit"
		disabled={!canSubmit}
		data-testid="multiday-submit"
		class="flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
	>
		{#if loading}
			<Spinner size="sm" />
		{/if}
		{m.multiday_submit()}
	</button>
</form>
