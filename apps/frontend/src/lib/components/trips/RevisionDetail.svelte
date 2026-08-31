<script lang="ts">
	import Modal from '$lib/components/ui/Modal.svelte';
	import RouteResults from '$lib/components/optimizer/RouteResults.svelte';
	import MultiDayItinerary from '$lib/components/optimizer/multiDay/MultiDayItinerary.svelte';
	import { getTripRevision } from '$lib/api/trips.js';
	import type { TripRevisionOut } from '$lib/types/index.js';
	import { formatDateTime } from '$lib/utils/format.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		open = $bindable(false),
		tripId,
		revision
	}: {
		open?: boolean;
		tripId: string;
		revision: number;
	} = $props();

	let detail = $state<TripRevisionOut | null>(null);
	let loadError = $state(false);
	let activeDayIndex = $state(0);

	$effect(() => {
		if (!open) return;
		detail = null;
		loadError = false;
		activeDayIndex = 0;
		getTripRevision(tripId, revision)
			.then((d) => (detail = d))
			.catch(() => (loadError = true));
	});
</script>

<Modal bind:open title={m.revision_detail_title({ revision })}>
	{#if loadError}
		<p class="text-sm text-red-600 dark:text-red-400">{m.revision_detail_error()}</p>
	{:else if !detail}
		<p class="text-sm text-zinc-500 dark:text-zinc-400">{m.revision_detail_loading()}</p>
	{:else}
		<p class="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
			{detail.source} · {formatDateTime(detail.recorded_at)}
		</p>
		<div class="max-h-[60vh] overflow-y-auto">
			{#if detail.plan_type === 'SINGLE_DAY'}
				<RouteResults result={detail.optimizer_response} />
			{:else}
				<MultiDayItinerary response={detail.multi_day_response} bind:activeDayIndex />
			{/if}
		</div>
	{/if}
</Modal>
