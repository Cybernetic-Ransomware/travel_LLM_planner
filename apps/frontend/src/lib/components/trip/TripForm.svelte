<script lang="ts">
	import type {
		PlaceOut,
		DayConfig,
		MultiDayRequest,
		TransportModeNoTransit
	} from '$lib/types/index.js';
	import DayConfigRow from './DayConfigRow.svelte';
	import PlaceAssignment from './PlaceAssignment.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import * as m from '$lib/paraglide/messages.js';

	let {
		places,
		loading = false,
		onsubmit
	}: {
		places: PlaceOut[];
		loading?: boolean;
		onsubmit: (request: MultiDayRequest) => void;
	} = $props();

	function isoDate(offsetDays = 0): string {
		return new Date(Date.now() + offsetDays * 86_400_000).toISOString().slice(0, 10);
	}

	function defaultDay(offset: number): DayConfig {
		return { date: isoDate(offset), day_start_hour: 8, day_end_hour: 20 };
	}

	let days = $state<DayConfig[]>([defaultDay(0)]);
	let selectedIds = $state<string[]>([]);
	let assignments = $state<Record<string, number | null>>({});
	let transportMode = $state<TransportModeNoTransit>('WALK');

	const canSubmit = $derived(days.length >= 1 && selectedIds.length >= 1 && !loading);

	const transportOptions = $derived([
		{ value: 'WALK', label: m.trip_walk() },
		{ value: 'DRIVE', label: m.trip_drive() },
		{ value: 'BICYCLE', label: m.trip_bicycle() }
	]);

	function addDay() {
		days = [...days, defaultDay(days.length)];
	}

	function removeDay(index: number) {
		days = days.filter((_, i) => i !== index);
		const updated: Record<string, number | null> = {};
		for (const [id, day] of Object.entries(assignments)) {
			updated[id] = day !== null && day >= days.length ? null : day;
		}
		assignments = updated;
	}

	function updateDay(index: number, updated: DayConfig) {
		days = days.map((d, i) => (i === index ? updated : d));
	}

	function togglePlace(id: string) {
		if (selectedIds.includes(id)) {
			selectedIds = selectedIds.filter((s) => s !== id);
			const updated = { ...assignments };
			delete updated[id];
			assignments = updated;
		} else {
			selectedIds = [...selectedIds, id];
		}
	}

	function assignPlace(placeId: string, dayIndex: number | null) {
		assignments = { ...assignments, [placeId]: dayIndex };
	}

	function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (!canSubmit) return;
		onsubmit({
			days,
			places: selectedIds.map((id) => ({
				place_id: id,
				day_preferences:
					assignments[id] !== undefined && assignments[id] !== null
						? [{ day_index: assignments[id] as number }]
						: []
			})),
			transport_mode: transportMode
		});
	}
</script>

<form
	onsubmit={handleSubmit}
	class="flex flex-col gap-4 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
>
	<div class="flex flex-col gap-2">
		<div class="flex items-center justify-between">
			<span class="text-xs font-medium text-zinc-700 dark:text-zinc-300">{m.trip_days()}</span>
			<button
				type="button"
				onclick={addDay}
				data-testid="add-day"
				class="text-xs text-blue-600 hover:underline"
			>
				{m.trip_add_day()}
			</button>
		</div>

		{#each days as day, i (i)}
			<DayConfigRow
				config={day}
				index={i}
				canRemove={days.length > 1}
				onchange={(updated) => updateDay(i, updated)}
				onremove={() => removeDay(i)}
			/>
		{/each}
	</div>

	<div class="flex flex-col gap-1">
		<div class="flex items-center justify-between">
			<span class="text-xs font-medium text-zinc-700 dark:text-zinc-300">{m.trip_places()}</span>
			<span class="text-xs text-zinc-400 dark:text-zinc-500">{selectedIds.length} selected</span>
		</div>
		<PlaceAssignment
			{places}
			{days}
			{selectedIds}
			{assignments}
			ontoggle={togglePlace}
			onassign={assignPlace}
		/>
	</div>

	<div class="flex flex-col gap-1">
		<span class="text-xs font-medium text-zinc-700 dark:text-zinc-300">{m.trip_transport()}</span>
		<Select options={transportOptions} bind:value={transportMode} disabled={loading} />
	</div>

	<button
		type="submit"
		disabled={!canSubmit}
		data-testid="trip-submit"
		class="flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
	>
		{#if loading}
			<Spinner size="sm" />
		{/if}
		{m.trip_submit()}
	</button>
</form>
