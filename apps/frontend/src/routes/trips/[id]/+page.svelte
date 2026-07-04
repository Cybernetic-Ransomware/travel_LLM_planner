<script lang="ts">
	import type { PageData } from './$types.js';
	import RouteResults from '$lib/components/optimizer/RouteResults.svelte';
	import * as m from '$lib/paraglide/messages.js';

	let { data }: { data: PageData } = $props();

	let LeafletMap: typeof import('$lib/components/map/LeafletMap.svelte').default | null =
		$state(null);

	$effect(() => {
		if (!LeafletMap && data.trip) {
			import('$lib/components/map/LeafletMap.svelte').then((mod) => {
				LeafletMap = mod.default;
			});
		}
	});

	function formatSeconds(s: number): string {
		const h = Math.floor(s / 3600);
		const min = Math.floor((s % 3600) / 60);
		return h > 0 ? `${h}h ${min}min` : `${min}min`;
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
			<h1 class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{data.trip.name}</h1>
			<p class="text-sm text-zinc-500 dark:text-zinc-400">
				{m.trip_date()}: {data.trip.date}
				&nbsp;·&nbsp;
				{m.trip_created_at()}: {new Date(data.trip.created_at).toLocaleString()}
			</p>
		{/if}
	</div>

	{#if data.backendError}
		<div class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
			<p class="font-medium">{m.error_backend_title()}</p>
			<p class="mt-1">
				{data.backendError.message}
				<span class="text-red-500 dark:text-red-400">({data.backendError.status})</span>
			</p>
		</div>
	{:else if data.trip}
		<div class="flex min-h-0 flex-1 flex-col gap-4 md:flex-row">
			<div class="flex w-full flex-col gap-4 overflow-y-auto md:w-72 md:shrink-0">
				<div class="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
					<p class="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-400 dark:text-zinc-500">
						{m.trip_saved_route()}
					</p>
					<dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
						<dt class="text-zinc-500 dark:text-zinc-400">{m.trip_transport()}</dt>
						<dd class="font-medium text-zinc-900 dark:text-zinc-100">{data.trip.transport_mode}</dd>

						<dt class="text-zinc-500 dark:text-zinc-400">{m.trip_time_window()}</dt>
						<dd class="font-medium text-zinc-900 dark:text-zinc-100">
							{data.trip.day_start_hour}:00 – {data.trip.day_end_hour}:00
						</dd>

						<dt class="text-zinc-500 dark:text-zinc-400">{m.results_places_unit()}</dt>
						<dd class="font-medium text-zinc-900 dark:text-zinc-100">
							{data.trip.optimizer_response.steps.length}
						</dd>

						<dt class="text-zinc-500 dark:text-zinc-400">{m.results_travel_label()}</dt>
						<dd class="font-medium text-zinc-900 dark:text-zinc-100">
							{formatSeconds(data.trip.optimizer_response.total_travel_time_s)}
						</dd>

						<dt class="text-zinc-500 dark:text-zinc-400">{m.results_visits_label()}</dt>
						<dd class="font-medium text-zinc-900 dark:text-zinc-100">
							{data.trip.optimizer_response.total_visit_time_min} min
						</dd>

						<dt class="text-zinc-500 dark:text-zinc-400">{m.results_wait_label()}</dt>
						<dd class="font-medium text-zinc-900 dark:text-zinc-100">
							{data.trip.optimizer_response.total_wait_min} min
						</dd>
					</dl>
				</div>

				<RouteResults result={data.trip.optimizer_response} />
			</div>

			<div class="h-64 flex-1 isolate overflow-hidden rounded-lg border border-zinc-200 md:h-auto dark:border-zinc-800">
				{#if LeafletMap}
					<LeafletMap steps={data.trip.optimizer_response.steps} />
				{:else}
					<div class="flex h-full items-center justify-center text-sm text-zinc-400 dark:text-zinc-500">
						{m.map_loading()}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
