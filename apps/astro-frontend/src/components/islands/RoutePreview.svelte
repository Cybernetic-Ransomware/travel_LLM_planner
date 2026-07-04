<script lang="ts">
	import { onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { getActivePlaces, optimizeRoute, ApiError } from '../../lib/api/client';
	import type { PlaceOut, OptimizeResponse, TransportMode } from '../../lib/types';
	import LeafletMap from './LeafletMap.svelte';

	let places: PlaceOut[] = $state([]);
	const selectedIds = new SvelteSet<string>();
	let startHour: number = $state(9);
	let transportMode: TransportMode = $state('WALK');
	let placesLoading: boolean = $state(true);
	let optimizing: boolean = $state(false);
	let error: string | null = $state(null);
	let result: OptimizeResponse | null = $state(null);

	const canOptimize = $derived(selectedIds.size >= 2 && !optimizing);

	const resultPlaces = $derived.by(() => {
		if (!result) return [];
		const ids = new Set(result.steps.map((s) => s.place_id));
		return places.filter((p) => ids.has(p.id));
	});

	onMount(async () => {
		try {
			places = await getActivePlaces();
			places.forEach((p) => selectedIds.add(p.id));
		} catch (err) {
			error = err instanceof ApiError ? `Cannot load places: ${err.message}` : 'Failed to load places';
		} finally {
			placesLoading = false;
		}
	});

	function togglePlace(id: string) {
		if (selectedIds.has(id)) {
			selectedIds.delete(id);
		} else {
			selectedIds.add(id);
		}
	}

	async function planRoute() {
		error = null;
		result = null;
		optimizing = true;
		try {
			result = await optimizeRoute({
				place_ids: [...selectedIds],
				transport_mode: transportMode,
				day_start_hour: startHour
			});
		} catch (err) {
			error = err instanceof ApiError ? `Cannot plan route: ${err.message}` : 'Optimization failed';
		} finally {
			optimizing = false;
		}
	}

	function formatSeconds(s: number): string {
		const h = Math.floor(s / 3600);
		const m = Math.floor((s % 3600) / 60);
		return h > 0 ? `${h}h ${m}min` : `${m}min`;
	}

	function formatTime(t: string): string {
		return t.slice(0, 5);
	}
</script>

{#if placesLoading}
	<p class="text-gray-500">Loading places…</p>
{:else if places.length === 0 && !error}
	<p class="text-gray-500">
		No active places found. Mark at least 2 places as active in the Places screen.
	</p>
{:else}
	<div class="space-y-6">
		<section>
			<h2 class="mb-2 text-sm font-semibold text-gray-700">
				Places <span class="font-normal text-gray-500">({selectedIds.size} of {places.length} selected)</span>
			</h2>
			<ul class="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
				{#each places as place (place.id)}
					<li class="flex items-start gap-3 px-4 py-3">
						<input
							type="checkbox"
							id="place-{place.id}"
							checked={selectedIds.has(place.id)}
							onchange={() => togglePlace(place.id)}
							class="mt-0.5 cursor-pointer"
						/>
						<label for="place-{place.id}" class="cursor-pointer leading-snug">
							<span class="font-medium">{place.name ?? 'Unnamed'}</span>
							{#if place.address}
								<span class="ml-1 text-sm text-gray-500">{place.address}</span>
							{/if}
						</label>
					</li>
				{/each}
			</ul>
		</section>

		<section class="flex flex-wrap items-end gap-4">
			<label class="flex flex-col gap-1 text-sm font-medium text-gray-700">
				Start hour (0–23)
				<input
					type="number"
					min="0"
					max="23"
					bind:value={startHour}
					class="w-24 rounded-md border border-gray-300 px-3 py-1.5 text-sm"
				/>
			</label>

			<label class="flex flex-col gap-1 text-sm font-medium text-gray-700">
				Transport
				<select
					bind:value={transportMode}
					class="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
				>
					<option value="WALK">Walk</option>
					<option value="DRIVE">Drive</option>
					<option value="BICYCLE">Bicycle</option>
					<option value="TRANSIT">Transit</option>
				</select>
			</label>

			<button
				onclick={planRoute}
				disabled={!canOptimize}
				class="rounded-md bg-blue-600 px-5 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
			>
				{optimizing ? 'Planning…' : 'Plan route'}
			</button>
		</section>
	</div>
{/if}

{#if error}
	<div class="mt-6 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
		{error}
	</div>
{/if}

{#if result}
	<div class="mt-8 space-y-6">
		<section
			class="flex flex-wrap gap-6 rounded-lg border border-gray-200 bg-white px-5 py-4 text-sm"
		>
			<span><span class="font-semibold">Travel:</span> {formatSeconds(result.total_travel_time_s)}</span>
			<span><span class="font-semibold">Visits:</span> {result.total_visit_time_min}min</span>
			{#if result.total_wait_min > 0}
				<span><span class="font-semibold">Wait:</span> {result.total_wait_min}min</span>
			{/if}
		</section>

		<ol class="space-y-2">
			{#each result.steps as step, i (step.place_id)}
				<li class="flex items-start gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3">
					<span
						class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white"
					>
						{i + 1}
					</span>
					<div class="min-w-0 flex-1">
						<p class="font-medium">{step.name ?? step.place_id}</p>
						<p class="text-sm text-gray-500">
							{formatTime(step.arrival_time)} → {formatTime(step.departure_time)}{#if step.wait_min > 0} · wait {step.wait_min}min{/if}
						</p>
					</div>
				</li>
			{/each}
		</ol>

		{#if result.skipped.length > 0}
			<section>
				<h3 class="mb-2 text-sm font-semibold text-gray-700">
					Not included ({result.skipped.length})
				</h3>
				<ul class="space-y-1">
					{#each result.skipped as s (s.place_id)}
						<li class="text-sm text-gray-600">
							{s.name ?? s.place_id}
							<span class="text-gray-400">— {s.reason}</span>
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		<LeafletMap steps={result.steps} places={resultPlaces} />
	</div>
{/if}
