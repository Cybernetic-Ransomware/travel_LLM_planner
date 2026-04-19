<script lang="ts">
	import { getPlacesContext } from '$lib/state/context.svelte.js';
	import { optimizeTrip } from '$lib/api/optimizer.js';
	import { ApiError } from '$lib/api/client.js';
	import type { MultiDayRequest, MultiDayResponse } from '$lib/types/index.js';
	import TripForm from '$lib/components/trip/TripForm.svelte';
	import DayPlanCard from '$lib/components/trip/DayPlanCard.svelte';
	import Toast from '$lib/components/ui/Toast.svelte';

	import * as m from '$lib/paraglide/messages.js';

	const places = getPlacesContext();

	let result = $state<MultiDayResponse | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);

	let LeafletMap: typeof import('$lib/components/map/LeafletMap.svelte').default | null =
		$state(null);

	$effect(() => {
		if (!LeafletMap) {
			import('$lib/components/map/LeafletMap.svelte').then((m) => {
				LeafletMap = m.default;
			});
		}
	});

	const allSteps = $derived(result?.days.flatMap((d) => d.steps) ?? []);

	async function handleSubmit(request: MultiDayRequest) {
		loading = true;
		error = null;
		result = null;
		try {
			result = await optimizeTrip(request);
		} catch (err) {
			error = err instanceof ApiError ? err.detail : 'Trip planning failed.';
		} finally {
			loading = false;
		}
	}
</script>

<div class="flex h-full flex-col gap-4">
	<div>
		<h1 class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{m.nav_trip()}</h1>
		<p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{m.page_trip_subtitle()}</p>
	</div>

	{#if error}
		<Toast message={error} variant="error" onclose={() => (error = null)} />
	{/if}

	<div class="flex min-h-0 flex-1 flex-col gap-4 md:flex-row">
		<div class="flex w-full flex-col gap-4 overflow-y-auto md:w-80 md:shrink-0">
			<TripForm places={places.filtered} {loading} onsubmit={handleSubmit} />

			{#if result}
				<div class="flex flex-col gap-6">
					{#if result.unassigned.length > 0}
						<div class="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950">
							<p class="text-xs font-semibold text-amber-700 dark:text-amber-300">
								{result.unassigned.length} {m.results_places_unit()} {m.trip_unassigned_label()}
							</p>
							{#each result.unassigned as u (u.place_id)}
								<p class="text-xs text-zinc-600 dark:text-zinc-400">
									{u.name ?? u.place_id}
									<span class="text-zinc-400 dark:text-zinc-500">— {u.reason.replace(/_/g, ' ').toLowerCase()}</span>
								</p>
							{/each}
						</div>
					{/if}

					{#each result.days as dayPlan (dayPlan.day_index)}
						<DayPlanCard {dayPlan} />
					{/each}
				</div>
			{/if}
		</div>

		<div class="h-64 flex-1 isolate overflow-hidden rounded-lg border border-zinc-200 md:h-auto dark:border-zinc-800">
			{#if LeafletMap}
				<LeafletMap places={result ? [] : places.filtered} steps={allSteps} />
			{:else}
				<div class="flex h-full items-center justify-center text-sm text-zinc-400 dark:text-zinc-500">
					{m.map_loading()}
				</div>
			{/if}
		</div>
	</div>
</div>
