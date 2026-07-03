<script lang="ts">
	import { onMount } from 'svelte';
	import { getPlaces } from '../../lib/api/client';
	import type { PlaceOut, PlaceStats } from '../../lib/types';
	import StatCard from './StatCard.svelte';

	let places = $state<PlaceOut[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// withHours counts enrichment-provided opening hours; the SvelteKit panel counts
	// user-set preferred_hour_from instead — a deliberately different metric here.
	const stats = $derived<PlaceStats>({
		total: places.length,
		active: places.filter((p) => !p.skipped).length,
		enriched: places.filter((p) => p.enriched_at !== null).length,
		withHours: places.filter((p) => p.opening_hours !== null).length
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
	<p class="text-sm text-gray-500">Loading stats…</p>
{:else if error}
	<div class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
		Cannot load stats: {error}
	</div>
{:else}
	<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
		<StatCard label="Total places" value={stats.total} icon="📍" />
		<StatCard label="Active" value={stats.active} icon="✓" />
		<StatCard label="Enriched" value={stats.enriched} icon="★" />
		<StatCard label="With opening hours" value={stats.withHours} icon="⏰" />
	</div>
{/if}
