<script lang="ts">
	import { saveTrip } from '$lib/api/trips.js';
	import { ApiError } from '$lib/api/client.js';
	import Modal from '$lib/components/ui/Modal.svelte';
	import type { OptimizeRequest, OptimizeResponse, SaveTripRequest, TripOut } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		request,
		result,
		onsave,
		oncancel
	}: {
		request: OptimizeRequest;
		result: OptimizeResponse;
		onsave: (trip: TripOut) => void;
		oncancel: () => void;
	} = $props();

	function localDateString(): string {
		const d = new Date();
		const y = d.getFullYear();
		const mo = String(d.getMonth() + 1).padStart(2, '0');
		const day = String(d.getDate()).padStart(2, '0');
		return `${y}-${mo}-${day}`;
	}

	let name = $state('');
	let date = $state(localDateString());
	let saving = $state(false);
	let formError = $state<string | null>(null);

	async function handleSave() {
		if (!name.trim()) {
			formError = m.save_trip_name_required();
			return;
		}
		formError = null;
		saving = true;
		try {
			const payload: SaveTripRequest = {
					name: name.trim(),
					date,
					optimizer_request: request,
					optimizer_response: result
				};
			const trip = await saveTrip(payload);
			onsave(trip);
		} catch (err) {
			formError = err instanceof ApiError ? err.detail : 'Failed to save trip.';
		} finally {
			saving = false;
		}
	}
</script>

<Modal open={true} title={m.save_trip_title()} onclose={oncancel}>
	<div class="flex flex-col gap-4">
		<div class="flex flex-col gap-1.5">
			<label for="trip-name" class="text-sm font-medium text-zinc-700 dark:text-zinc-300">
				{m.save_trip_name_label()}
			</label>
			<input
				id="trip-name"
				type="text"
				bind:value={name}
				placeholder={m.save_trip_name_placeholder()}
				class="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder-zinc-500"
			/>
		</div>
		<div class="flex flex-col gap-1.5">
			<label for="trip-date" class="text-sm font-medium text-zinc-700 dark:text-zinc-300">
				{m.save_trip_date_label()}
			</label>
			<input
				id="trip-date"
				type="date"
				bind:value={date}
				class="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
			/>
		</div>
		{#if formError}
			<p class="text-sm text-red-600 dark:text-red-400">{formError}</p>
		{/if}
	</div>
	{#snippet footer()}
		<button
			onclick={oncancel}
			disabled={saving}
			class="rounded-lg px-4 py-2 text-sm font-medium text-zinc-600 hover:bg-zinc-100 disabled:opacity-50 dark:text-zinc-300 dark:hover:bg-zinc-800"
		>
			{m.save_trip_cancel()}
		</button>
		<button
			onclick={handleSave}
			disabled={saving}
			class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
		>
			{saving ? '…' : m.save_trip_submit()}
		</button>
	{/snippet}
</Modal>
