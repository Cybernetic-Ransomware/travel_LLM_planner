<script lang="ts">
	import { untrack } from 'svelte';
	import { optimizeTrip } from '$lib/api/optimizer.js';
	import { updateTrip } from '$lib/api/trips.js';
	import { ApiError } from '$lib/api/client.js';
	import type {
		MultiDayRequest,
		MultiDayResponse,
		MultiDaySaveTripRequest,
		PlaceOut,
		TripOut
	} from '$lib/types/index.js';
	import {
		defaultEditableState,
		buildMultiDayRequest,
		type MultiDayEditableState
	} from './buildMultiDayRequest.js';
	import {
		hydrateEditableState,
		countMissingPrefillPlaces,
		type MultiDayOptimizerPrefill
	} from './hydrateMultiDayState.js';
	import MultiDayForm from './MultiDayForm.svelte';
	import MultiDayItinerary from './MultiDayItinerary.svelte';
	import SaveMultiDayTripForm from '../SaveMultiDayTripForm.svelte';
	import Toast from '$lib/components/ui/Toast.svelte';
	import * as m from '$lib/paraglide/messages.js';

	let {
		places,
		hasLoadError = false,
		prefill
	}: {
		places: PlaceOut[];
		hasLoadError?: boolean;
		prefill: MultiDayOptimizerPrefill | null;
	} = $props();

	const availablePlaceIds = $derived(new Set(places.map((p) => p.id)));

	// The sole stateful owner of the multi-day lifecycle — no child holds these directly, only handleConfigChange mutates.
	let editableState = $state<MultiDayEditableState>(
		untrack(() =>
			prefill
				? hydrateEditableState(prefill.multiDayRequest, availablePlaceIds)
				: defaultEditableState()
		)
	);
	let lastOptimizedRequest = $state<MultiDayRequest | null>(
		untrack(() => prefill?.multiDayRequest ?? null)
	);
	let result = $state<MultiDayResponse | null>(untrack(() => prefill?.multiDayResponse ?? null));
	let isStale = $state(false);
	let activeDayIndex = $state(0);

	let loading = $state(false);
	let updating = $state(false);
	let error = $state<string | null>(null);
	let showSaveForm = $state(false);
	let saveSuccess = $state<string | null>(null);

	const missingPrefillPlaceCount = untrack(() =>
		prefill ? countMissingPrefillPlaces(prefill.multiDayRequest, availablePlaceIds) : 0
	);
	let prefillMissingCount = $state(missingPrefillPlaceCount);
	let prefillNotice = $state<string | null>(
		untrack(() => (prefill ? m.optimizer_prefill_notice({ name: prefill.tripName }) : null))
	);

	let MultiDayLeafletMap:
		| typeof import('$lib/components/map/MultiDayLeafletMap.svelte').default
		| null = $state(null);

	$effect(() => {
		if (!MultiDayLeafletMap && result !== null) {
			import('$lib/components/map/MultiDayLeafletMap.svelte').then((mod) => {
				MultiDayLeafletMap = mod.default;
			});
		}
	});

	const activeDay = $derived(result?.days[activeDayIndex] ?? null);

	// result + lastOptimizedRequest always form a consistent pair; an edit only flags isStale, it never clears result.
	function handleConfigChange(next: MultiDayEditableState) {
		editableState = next;
		if (result !== null) isStale = true;
	}

	async function runOptimization(request: MultiDayRequest): Promise<boolean> {
		loading = true;
		error = null;
		try {
			const response = await optimizeTrip(request);
			result = response;
			lastOptimizedRequest = request;
			isStale = false;
			activeDayIndex =
				response.days.length > 0 ? Math.min(activeDayIndex, response.days.length - 1) : 0;
			return true;
		} catch (err) {
			if (err instanceof ApiError) {
				const d = err.detail.toLowerCase();
				if (err.status === 504 || d.includes('timed out')) {
					error = m.optimizer_error_timeout();
				} else if (d.includes('permission_denied') || d.includes('permission denied')) {
					error = m.optimizer_error_api_key();
				} else {
					error = err.detail;
				}
			} else {
				error = m.multiday_optimize_failed();
			}
			return false;
		} finally {
			loading = false;
		}
	}

	function handleFormSubmit() {
		if (loading) return;
		saveSuccess = null;
		void runOptimization(buildMultiDayRequest(editableState));
	}

	function handleTripSaved(trip: TripOut) {
		showSaveForm = false;
		saveSuccess = m.save_trip_success({ name: trip.name });
	}

	async function handleUpdateTrip() {
		if (!prefill || !result || !lastOptimizedRequest || isStale || updating) return;
		updating = true;
		error = null;
		saveSuccess = null;
		try {
			const payload: MultiDaySaveTripRequest = {
				name: prefill.tripName,
				multi_day_request: lastOptimizedRequest,
				multi_day_response: result
			};
			const trip = await updateTrip(prefill.tripId, payload);
			saveSuccess = m.update_trip_success({ name: trip.name });
		} catch (err) {
			error = err instanceof ApiError ? err.detail : m.update_trip_failed();
		} finally {
			updating = false;
		}
	}
</script>

<div class="flex flex-col gap-4">
	{#if prefillNotice}
		<Toast message={prefillNotice} variant="info" onclose={() => (prefillNotice = null)} />
	{/if}

	{#if prefillMissingCount > 0}
		<Toast
			message={m.optimizer_prefill_missing_places({ count: prefillMissingCount })}
			variant="warning"
			onclose={() => (prefillMissingCount = 0)}
		/>
	{/if}

	{#if error}
		<Toast message={error} variant="error" onclose={() => (error = null)} />
	{/if}

	{#if saveSuccess}
		<Toast message={saveSuccess} variant="success" onclose={() => (saveSuccess = null)} />
	{/if}

	<div class="flex min-h-0 flex-1 flex-col gap-4 md:flex-row">
		<div class="flex w-full flex-col gap-4 overflow-y-auto md:w-96 md:shrink-0">
			<MultiDayForm
				state={editableState}
				{places}
				{hasLoadError}
				loading={loading || updating}
				onchange={handleConfigChange}
				onsubmit={handleFormSubmit}
			/>

			{#if result}
				{#if isStale}
					<p
						class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300"
						data-testid="stale-notice"
					>
						{m.multiday_stale_notice()}
					</p>
				{/if}

				<MultiDayItinerary response={result} bind:activeDayIndex />

				{#if prefill}
					<button
						onclick={handleUpdateTrip}
						disabled={updating || isStale}
						class="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
					>
						{updating ? '…' : m.optimizer_update_trip()}
					</button>
				{/if}

				<button
					onclick={() => (showSaveForm = true)}
					disabled={isStale}
					class="w-full rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
				>
					{prefill ? m.optimizer_save_as_new() : m.optimizer_save_trip()}
				</button>
			{/if}
		</div>

		<div
			class="isolate h-64 flex-1 overflow-hidden rounded-lg border border-zinc-200 md:h-auto dark:border-zinc-800"
		>
			{#if activeDay && MultiDayLeafletMap}
				<MultiDayLeafletMap {activeDay} />
			{:else}
				<div
					class="flex h-full items-center justify-center text-sm text-zinc-400 dark:text-zinc-500"
				>
					{m.map_loading()}
				</div>
			{/if}
		</div>
	</div>
</div>

{#if showSaveForm && result && lastOptimizedRequest}
	<SaveMultiDayTripForm
		request={lastOptimizedRequest}
		response={result}
		onsave={handleTripSaved}
		oncancel={() => (showSaveForm = false)}
	/>
{/if}
