<script lang="ts">
	import MetricCard from '$lib/components/ui/MetricCard.svelte';
	import * as m from '$lib/paraglide/messages.js';

	let {
		total,
		active,
		enriched,
		withHours
	}: {
		total: number;
		active: number;
		enriched: number;
		withHours: number;
	} = $props();
</script>

<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
	<MetricCard label={m.places_stat_total()} value={total} icon="📍" />
	<MetricCard label={m.places_stat_active()} value={active} icon="✓" />
	<MetricCard label={m.places_stat_enriched()} value={enriched} icon="★" />
	<MetricCard label={m.places_stat_with_hours()} value={withHours} icon="⏰" />
</div>
