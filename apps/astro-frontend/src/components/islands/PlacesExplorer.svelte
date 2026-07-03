<script lang="ts">
	import { onMount } from 'svelte';
	import { getPlaces } from '../../lib/api/client';
	import type { PlaceOut, PlaceStats } from '../../lib/types';
	import LeafletMap from './LeafletMap.svelte';
	import PlaceFilters from './PlaceFilters.svelte';
	import PlaceTable from './PlaceTable.svelte';
	import StatCard from './StatCard.svelte';

	let places = $state<PlaceOut[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let filterSkipped = $state<boolean | null>(null);
	let filterListName = $state<string | null>(null);
	let showMap = $state(false);

	const filtered = $derived(
		places.filter((p) => {
			if (filterSkipped !== null && p.skipped !== filterSkipped) return false;
			if (filterListName && p.list_name !== filterListName) return false;
			return true;
		})
	);

	const listNames = $derived(
		[...new Set(places.map((p) => p.list_name).filter((n): n is string => n !== null))].sort()
	);

	const stats = $derived<PlaceStats>({
		total: filtered.length,
		active: filtered.filter((p) => !p.skipped).length,
		enriched: filtered.filter((p) => p.enriched_at !== null).length,
		withHours: filtered.filter((p) => p.opening_hours !== null).length
	});

	onMount(async () => {
		try {
			places = await getPlaces();
		} catch (err) {
			error = (err as Error).message;
		} finally {
			loading = false;
		}
	});
</script>

{#if loading}
	<p class="text-sm text-gray-500">Loading places…</p>
{:else if error}
	<div class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
		Cannot load places: {error}
	</div>
{:else}
	<div class="space-y-4">
		<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
			<StatCard label="Total places" value={stats.total} icon="📍" />
			<StatCard label="Active" value={stats.active} icon="✓" />
			<StatCard label="Enriched" value={stats.enriched} icon="★" />
			<StatCard label="With opening hours" value={stats.withHours} icon="⏰" />
		</div>

		<div class="flex flex-wrap items-center justify-between gap-3">
			<PlaceFilters bind:filterSkipped bind:filterListName {listNames} />
			<button
				type="button"
				class="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm hover:bg-gray-50"
				onclick={() => (showMap = !showMap)}
			>
				{showMap ? 'Hide map' : 'Show map'}
			</button>
		</div>

		{#if showMap}
			<div class="h-[500px] overflow-hidden rounded-lg border border-gray-200">
				<LeafletMap places={filtered} />
			</div>
		{/if}

		<PlaceTable places={filtered} />
	</div>
{/if}
