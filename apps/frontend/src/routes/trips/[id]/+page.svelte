<script lang="ts">
	import { goto } from '$app/navigation';
	import type { PageData } from './$types.js';
	import RouteResults from '$lib/components/optimizer/RouteResults.svelte';
	import MultiDayItinerary from '$lib/components/optimizer/multiDay/MultiDayItinerary.svelte';
	import DeleteTripDialog from '$lib/components/trips/DeleteTripDialog.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Toast from '$lib/components/ui/Toast.svelte';
	import { deleteTrip } from '$lib/api/trips.js';
	import { formatDurationSeconds, formatDateTime } from '$lib/utils/format.js';
	import * as m from '$lib/paraglide/messages.js';

	let { data }: { data: PageData } = $props();

	let showDeleteDialog = $state(false);
	let deleting = $state(false);
	let deleteError = $state<string | null>(null);
	let activeDayIndex = $state(0);

	let LeafletMap: typeof import('$lib/components/map/LeafletMap.svelte').default | null =
		$state(null);
	let MultiDayLeafletMap:
		| typeof import('$lib/components/map/MultiDayLeafletMap.svelte').default
		| null = $state(null);

	$effect(() => {
		if (!data.trip) return;
		if (data.trip.plan_type === 'SINGLE_DAY' && !LeafletMap) {
			import('$lib/components/map/LeafletMap.svelte').then((mod) => {
				LeafletMap = mod.default;
			});
		}
		if (data.trip.plan_type === 'MULTI_DAY' && !MultiDayLeafletMap) {
			import('$lib/components/map/MultiDayLeafletMap.svelte').then((mod) => {
				MultiDayLeafletMap = mod.default;
			});
		}
	});

	const activeDay = $derived(
		data.trip?.plan_type === 'MULTI_DAY'
			? (data.trip.multi_day_response.days[activeDayIndex] ?? null)
			: null
	);

	async function confirmDelete() {
		if (!data.trip) return;
		deleting = true;
		deleteError = null;
		try {
			await deleteTrip(data.trip.id);
			await goto(`/trips?deleted=${encodeURIComponent(data.trip.name)}`);
		} catch {
			showDeleteDialog = false;
			deleteError = m.trip_delete_error();
		} finally {
			deleting = false;
		}
	}
</script>

<div class="flex h-full flex-col gap-4">
	<div class="flex flex-col gap-1">
		<a
			href="/trips"
			class="w-fit text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
		>
			← {m.nav_trips()}
		</a>
		{#if data.trip}
			{@const trip = data.trip}
			<div class="flex flex-wrap items-start justify-between gap-3">
				<div>
					<h1 class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{trip.name}</h1>
					<p class="text-sm text-zinc-500 dark:text-zinc-400">
						{#if trip.plan_type === 'SINGLE_DAY'}
							{m.trip_date()}: {trip.date}
						{:else}
							{m.trip_date_range()}: {trip.start_date} – {trip.end_date}
						{/if}
						&nbsp;·&nbsp;
						{m.trip_created_at()}: {formatDateTime(trip.created_at)}
					</p>
				</div>
				<div class="flex items-center gap-2">
					<a
						href="/optimizer?from={trip.id}"
						class="inline-flex items-center gap-2 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
					>
						{m.trip_open_in_optimizer()}
					</a>
					<Button variant="danger" onclick={() => (showDeleteDialog = true)}>
						{m.trip_delete()}
					</Button>
				</div>
			</div>
		{/if}
	</div>

	{#if deleteError}
		<Toast message={deleteError} variant="error" onclose={() => (deleteError = null)} />
	{/if}

	{#if data.backendError}
		<div
			class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
		>
			<p class="font-medium">{m.error_backend_title()}</p>
			<p class="mt-1">
				{data.backendError.message}
				<span class="text-red-500 dark:text-red-400">({data.backendError.status})</span>
			</p>
		</div>
	{:else if data.trip}
		{@const trip = data.trip}
		{#if trip.plan_type === 'SINGLE_DAY'}
			<div class="flex min-h-0 flex-1 flex-col gap-4 md:flex-row">
				<div class="flex w-full flex-col gap-4 overflow-y-auto md:w-72 md:shrink-0">
					<div
						class="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
					>
						<p
							class="mb-3 text-xs font-semibold tracking-wide text-zinc-400 uppercase dark:text-zinc-500"
						>
							{m.trip_saved_route()}
						</p>
						<dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
							<dt class="text-zinc-500 dark:text-zinc-400">{m.trip_transport()}</dt>
							<dd class="font-medium text-zinc-900 dark:text-zinc-100">{trip.transport_mode}</dd>

							<dt class="text-zinc-500 dark:text-zinc-400">{m.trip_time_window()}</dt>
							<dd class="font-medium text-zinc-900 dark:text-zinc-100">
								{trip.day_start_hour}:00 – {trip.day_end_hour}:00
							</dd>

							<dt class="text-zinc-500 dark:text-zinc-400">{m.results_places_unit()}</dt>
							<dd class="font-medium text-zinc-900 dark:text-zinc-100">
								{trip.optimizer_response.steps.length}
							</dd>

							<dt class="text-zinc-500 dark:text-zinc-400">{m.results_travel_label()}</dt>
							<dd class="font-medium text-zinc-900 dark:text-zinc-100">
								{formatDurationSeconds(trip.optimizer_response.total_travel_time_s)}
							</dd>

							<dt class="text-zinc-500 dark:text-zinc-400">{m.results_visits_label()}</dt>
							<dd class="font-medium text-zinc-900 dark:text-zinc-100">
								{trip.optimizer_response.total_visit_time_min} min
							</dd>

							<dt class="text-zinc-500 dark:text-zinc-400">{m.results_wait_label()}</dt>
							<dd class="font-medium text-zinc-900 dark:text-zinc-100">
								{trip.optimizer_response.total_wait_min} min
							</dd>
						</dl>
					</div>

					<RouteResults result={trip.optimizer_response} />
				</div>

				<div
					class="isolate h-64 flex-1 overflow-hidden rounded-lg border border-zinc-200 md:h-auto dark:border-zinc-800"
				>
					{#if LeafletMap}
						<LeafletMap steps={trip.optimizer_response.steps} />
					{:else}
						<div
							class="flex h-full items-center justify-center text-sm text-zinc-400 dark:text-zinc-500"
						>
							{m.map_loading()}
						</div>
					{/if}
				</div>
			</div>
		{:else}
			<div class="flex min-h-0 flex-1 flex-col gap-4 md:flex-row">
				<div class="flex w-full flex-col gap-4 overflow-y-auto md:w-96 md:shrink-0">
					<div
						class="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
					>
						<p
							class="mb-3 text-xs font-semibold tracking-wide text-zinc-400 uppercase dark:text-zinc-500"
						>
							{m.trip_saved_route()}
						</p>
						<dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
							<dt class="text-zinc-500 dark:text-zinc-400">{m.trip_date_range()}</dt>
							<dd class="font-medium text-zinc-900 dark:text-zinc-100">
								{trip.start_date} – {trip.end_date}
							</dd>

							<dt class="text-zinc-500 dark:text-zinc-400">{m.trip_days()}</dt>
							<dd class="font-medium text-zinc-900 dark:text-zinc-100">{trip.num_days}</dd>

							<dt class="text-zinc-500 dark:text-zinc-400">{m.trip_transport()}</dt>
							<dd class="font-medium text-zinc-900 dark:text-zinc-100">{trip.transport_mode}</dd>
						</dl>
					</div>

					<MultiDayItinerary response={trip.multi_day_response} bind:activeDayIndex />
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
		{/if}
	{/if}
</div>

{#if data.trip}
	<DeleteTripDialog
		bind:open={showDeleteDialog}
		tripName={data.trip.name}
		loading={deleting}
		onconfirm={confirmDelete}
	/>
{/if}
