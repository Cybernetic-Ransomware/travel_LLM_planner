<script lang="ts">
	import { saveTrip } from '$lib/api/trips.js';
	import { ApiError } from '$lib/api/client.js';
	import Modal from '$lib/components/ui/Modal.svelte';
	import type {
		MultiDayRequest,
		MultiDayResponse,
		MultiDaySaveTripRequest,
		TripOut
	} from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		request,
		response,
		onsave,
		oncancel
	}: {
		request: MultiDayRequest;
		response: MultiDayResponse;
		onsave: (trip: TripOut) => void;
		oncancel: () => void;
	} = $props();

	let name = $state('');
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
			const payload: MultiDaySaveTripRequest = {
				name: name.trim(),
				multi_day_request: request,
				multi_day_response: response
			};
			const trip = await saveTrip(payload);
			onsave(trip);
		} catch (err) {
			formError = err instanceof ApiError ? err.detail : m.save_trip_failed();
		} finally {
			saving = false;
		}
	}
</script>

<Modal open={true} title={m.save_trip_title()} onclose={oncancel}>
	<div class="flex flex-col gap-4">
		<div class="flex flex-col gap-1.5">
			<label for="multiday-trip-name" class="text-sm font-medium text-zinc-700 dark:text-zinc-300">
				{m.save_trip_name_label()}
			</label>
			<input
				id="multiday-trip-name"
				type="text"
				bind:value={name}
				placeholder={m.save_trip_name_placeholder()}
				class="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder-zinc-500"
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
