<script lang="ts">
	import { untrack } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import type { PageData } from './$types.js';
	import { optimizeRoute } from '$lib/api/optimizer.js';
	import { updateTrip } from '$lib/api/trips.js';
	import { patchPlace } from '$lib/api/gmaps.js';
	import { ApiError } from '$lib/api/client.js';
	import type { OptimizeRequest, OptimizeResponse, PlaceOut, TripOut } from '$lib/types/index.js';
	import RouteForm from '$lib/components/optimizer/RouteForm.svelte';
	import RouteResults from '$lib/components/optimizer/RouteResults.svelte';
	import SaveTripForm from '$lib/components/optimizer/SaveTripForm.svelte';
	import Toast from '$lib/components/ui/Toast.svelte';

	import * as m from '$lib/paraglide/messages.js';

	let { data }: { data: PageData } = $props();

	let places = $state<PlaceOut[]>(untrack(() => data.places));

	let selectedIds = $state<string[]>(
		untrack(() =>
			data.prefill
				? data.prefill.selectedPlaceIds.filter((id) => places.some((p) => p.id === id))
				: places.map((p) => p.id)
		)
	);
	let result = $state<OptimizeResponse | null>(null);
	let lastRequest = $state<OptimizeRequest | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let showSaveForm = $state(false);
	let saveSuccess = $state<string | null>(null);
	let updating = $state(false);
	let preferenceNotice = $state<{ message: string; variant: 'success' | 'warning' } | null>(null);
	let promotingPlaceId = $state<string | null>(null);
	const promotedPlaceIds = new SvelteSet<string>();
	let prefillNotice = $state<string | null>(
		untrack(() =>
			data.prefill ? m.optimizer_prefill_notice({ name: data.prefill.tripName }) : null
		)
	);
	let prefillFailed = $state(untrack(() => data.prefillFailed));
	let prefillMissingCount = $state(untrack(() => data.missingPrefillPlaceCount));

	let LeafletMap: typeof import('$lib/components/map/LeafletMap.svelte').default | null =
		$state(null);

	$effect(() => {
		if (!LeafletMap && (places.length > 0 || result !== null)) {
			import('$lib/components/map/LeafletMap.svelte').then((m) => {
				LeafletMap = m.default;
			});
		}
	});

	const requestedPlaces = $derived.by(() => {
		if (!lastRequest) return [];
		const ids = new Set(lastRequest.place_ids);
		return places.filter((p) => ids.has(p.id));
	});

	const mapPlaces = $derived(result ? [] : places);
	const mapSteps = $derived(result?.steps ?? []);
	const mapSelectedIds = $derived(new Set(selectedIds));

	const placesLoadError = $derived(
		data.backendError ? `${data.backendError.message} (${data.backendError.status})` : null
	);

	async function runOptimization(request: OptimizeRequest): Promise<boolean> {
		loading = true;
		error = null;
		try {
			result = await optimizeRoute(request);
			promotedPlaceIds.clear();
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
				error = 'Optimization failed.';
			}
			return false;
		} finally {
			loading = false;
		}
	}

	async function handleSubmit(request: OptimizeRequest) {
		lastRequest = request;
		result = null;
		saveSuccess = null;
		preferenceNotice = null;
		await runOptimization(request);
	}

	function handleTripSaved(trip: TripOut) {
		showSaveForm = false;
		saveSuccess = m.save_trip_success({ name: trip.name });
	}

	async function handleUpdateTrip() {
		if (!data.prefill || !result || !lastRequest) return;
		updating = true;
		error = null;
		saveSuccess = null;
		try {
			const trip = await updateTrip(data.prefill.tripId, {
				name: data.prefill.tripName,
				date: data.prefill.tripDate,
				optimizer_request: lastRequest,
				optimizer_response: result
			});
			saveSuccess = m.update_trip_success({ name: trip.name });
		} catch (err) {
			error = err instanceof ApiError ? err.detail : m.update_trip_failed();
		} finally {
			updating = false;
		}
	}

	async function handleMarkMustSee(placeId: string) {
		if (!lastRequest || promotingPlaceId !== null) return;
		error = null;
		preferenceNotice = null;
		promotingPlaceId = placeId;
		try {
			const updatedPlace = await patchPlace(placeId, { priority: 'must_see' });
			places = places.map((p) => (p.id === placeId ? updatedPlace : p));
			promotedPlaceIds.add(placeId);
			const rerunSucceeded = await runOptimization(lastRequest);
			preferenceNotice = rerunSucceeded
				? { message: m.optimizer_preference_updated_and_rerun(), variant: 'success' }
				: { message: m.optimizer_preference_updated_rerun_failed(), variant: 'warning' };
		} catch (err) {
			error = err instanceof ApiError ? err.detail : m.optimizer_preference_update_failed();
		} finally {
			promotingPlaceId = null;
		}
	}
</script>

<div class="flex h-full flex-col gap-4">
	<div>
		<h1 class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
			{m.page_optimizer_title()}
		</h1>
		<p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{m.page_optimizer_subtitle()}</p>
	</div>

	{#if placesLoadError}
		<Toast message={placesLoadError} variant="error" />
	{/if}

	{#if prefillFailed}
		<Toast
			message={m.optimizer_prefill_failed()}
			variant="error"
			onclose={() => (prefillFailed = false)}
		/>
	{/if}

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

	{#if preferenceNotice}
		<Toast
			message={preferenceNotice.message}
			variant={preferenceNotice.variant}
			onclose={() => (preferenceNotice = null)}
		/>
	{/if}

	<div class="flex min-h-0 flex-1 flex-col gap-4 md:flex-row">
		<div class="flex w-full flex-col gap-4 overflow-y-auto md:w-72 md:shrink-0">
			<RouteForm
				{places}
				hasLoadError={data.backendError !== null}
				bind:selectedIds
				{loading}
				initialTransportMode={data.prefill?.transportMode}
				initialDayStartHour={data.prefill?.dayStartHour}
				initialDayEndHour={data.prefill?.dayEndHour}
				onsubmit={handleSubmit}
			/>

			{#if result}
				<RouteResults
					{result}
					places={requestedPlaces}
					onmarkmustsee={handleMarkMustSee}
					{promotedPlaceIds}
					{promotingPlaceId}
				/>

				{#if data.prefill}
					<button
						onclick={handleUpdateTrip}
						disabled={updating}
						class="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
					>
						{updating ? '…' : m.optimizer_update_trip()}
					</button>
				{/if}

				<button
					onclick={() => (showSaveForm = true)}
					class="w-full rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
				>
					{data.prefill ? m.optimizer_save_as_new() : m.optimizer_save_trip()}
				</button>
			{/if}
		</div>

		<div
			class="isolate h-64 flex-1 overflow-hidden rounded-lg border border-zinc-200 md:h-auto dark:border-zinc-800"
		>
			{#if LeafletMap}
				<LeafletMap places={mapPlaces} steps={mapSteps} selectedIds={mapSelectedIds} />
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

{#if showSaveForm && result && lastRequest}
	<SaveTripForm
		request={lastRequest}
		{result}
		onsave={handleTripSaved}
		oncancel={() => (showSaveForm = false)}
	/>
{/if}
