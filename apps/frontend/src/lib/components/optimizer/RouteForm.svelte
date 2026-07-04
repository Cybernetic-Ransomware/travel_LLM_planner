<script lang="ts">
	import type { PlaceOut, OptimizeRequest, TransportMode } from '$lib/types/index.js';
	import Select from '$lib/components/ui/Select.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import * as m from '$lib/paraglide/messages.js';

	let {
		places,
		hasLoadError = false,
		selectedIds = $bindable<string[]>([]),
		loading = false,
		onsubmit
	}: {
		places: PlaceOut[];
		hasLoadError?: boolean;
		selectedIds?: string[];
		loading?: boolean;
		onsubmit: (request: OptimizeRequest) => void;
	} = $props();

	let transportMode = $state<TransportMode>('WALK');
	let dayStartHour = $state(8);
	let dayEndHour = $state(20);

	const validHours = $derived(
		dayStartHour >= 0 &&
		dayStartHour <= 23 &&
		dayEndHour >= 1 &&
		dayEndHour <= 24 &&
		dayStartHour < dayEndHour
	);
	const canSubmit = $derived(selectedIds.length >= 2 && validHours && !loading);

	const transportOptions = $derived([
		{ value: 'WALK', label: m.optimizer_walk() },
		{ value: 'DRIVE', label: m.optimizer_drive() },
		{ value: 'BICYCLE', label: m.optimizer_bicycle() },
		{ value: 'TRANSIT', label: m.optimizer_transit() }
	]);

	const allSelected = $derived(
		places.length > 0 && places.every((p) => selectedIds.includes(p.id))
	);

	function togglePlace(id: string) {
		if (selectedIds.includes(id)) {
			selectedIds = selectedIds.filter((s) => s !== id);
		} else {
			selectedIds = [...selectedIds, id];
		}
	}

	function toggleAll() {
		if (allSelected) {
			selectedIds = [];
		} else {
			selectedIds = places.map((p) => p.id);
		}
	}

	function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (!canSubmit) return;
		onsubmit({
			place_ids: selectedIds,
			transport_mode: transportMode,
			day_start_hour: dayStartHour,
			day_end_hour: dayEndHour
		});
	}
</script>

<form
	onsubmit={handleSubmit}
	class="flex flex-col gap-4 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
>
	<div class="flex flex-col gap-1">
		<div class="flex items-center justify-between">
			<span class="text-xs font-medium text-zinc-700 dark:text-zinc-300">{m.optimizer_places()}</span>
			<button
				type="button"
				onclick={toggleAll}
				class="text-xs text-blue-600 hover:underline"
				data-testid="toggle-all"
			>
				{allSelected ? m.optimizer_clear_all() : m.optimizer_select_all()}
			</button>
		</div>

		<div class="max-h-48 overflow-y-auto rounded-md border border-zinc-200 dark:border-zinc-700 dark:bg-zinc-800">
			{#each places as place (place.id)}
				<label
					class="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-700"
				>
					<input
						type="checkbox"
						checked={selectedIds.includes(place.id)}
						onchange={() => togglePlace(place.id)}
						class="accent-blue-600"
					/>
					<span class="truncate text-zinc-800 dark:text-zinc-200">{place.name ?? place.id}</span>
					{#if place.list_name}
						<span class="ml-auto shrink-0 text-xs text-zinc-400">{place.list_name}</span>
					{/if}
				</label>
			{:else}
				{#if hasLoadError}
					<p class="px-3 py-4 text-center text-xs text-zinc-400">{m.optimizer_places_load_error()}</p>
				{:else}
					<p class="px-3 py-4 text-center text-xs text-zinc-400">{m.optimizer_no_active_places()}</p>
				{/if}
			{/each}
		</div>

		<p class="text-xs text-zinc-400 dark:text-zinc-500">
			{selectedIds.length} of {places.length} selected
		</p>
	</div>

	<div class="flex flex-col gap-1">
		<label class="text-xs font-medium text-zinc-700 dark:text-zinc-300" for="transport-mode">
			{m.optimizer_transport()}
		</label>
		<Select options={transportOptions} bind:value={transportMode} disabled={loading} />
	</div>

	<div class="grid grid-cols-2 gap-2">
		<div class="flex flex-col gap-1">
			<label class="text-xs font-medium text-zinc-700 dark:text-zinc-300" for="start-hour">
				{m.optimizer_start_hour()}
			</label>
			<input
				id="start-hour"
				type="number"
				min="0"
				max="23"
				bind:value={dayStartHour}
				disabled={loading}
				class="rounded-md border border-zinc-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
			/>
		</div>
		<div class="flex flex-col gap-1">
			<label class="text-xs font-medium text-zinc-700 dark:text-zinc-300" for="end-hour">
				{m.optimizer_end_hour()}
			</label>
			<input
				id="end-hour"
				type="number"
				min="1"
				max="24"
				bind:value={dayEndHour}
				disabled={loading}
				class="rounded-md border border-zinc-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
			/>
		</div>
	</div>

	<button
		type="submit"
		disabled={!canSubmit}
		data-testid="optimize-submit"
		class="flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
	>
		{#if loading}
			<Spinner size="sm" />
		{/if}
		{m.optimizer_submit()}
	</button>

	{#if places.length === 1}
		<p class="text-center text-xs text-zinc-400 dark:text-zinc-500">{m.optimizer_one_place()}</p>
	{:else if selectedIds.length < 2}
		<p class="text-center text-xs text-zinc-400 dark:text-zinc-500">{m.optimizer_min_places_hint()}</p>
	{:else if !validHours}
		<p class="text-center text-xs text-zinc-400 dark:text-zinc-500">{m.optimizer_invalid_hours()}</p>
	{/if}
</form>
