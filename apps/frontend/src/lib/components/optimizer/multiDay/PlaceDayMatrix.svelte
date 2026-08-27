<script lang="ts">
	import { SvelteMap } from 'svelte/reactivity';
	import type { DaySlot, PlaceOut } from '$lib/types/index.js';
	import { toggleDaySlot, checkedDayIndices, placeDaySelectionKind } from './placeDaySlots.js';
	import DayCheckboxGroup from './DayCheckboxGroup.svelte';
	import * as m from '$lib/paraglide/messages.js';

	let {
		places,
		numDays,
		placeSelections,
		disabled = false,
		onchange
	}: {
		places: PlaceOut[];
		numDays: number;
		placeSelections: Map<string, DaySlot[]>;
		disabled?: boolean;
		onchange: (next: Map<string, DaySlot[]>) => void;
	} = $props();

	const kindLabels: Record<ReturnType<typeof placeDaySelectionKind>, () => string> = {
		AUTO: m.multiday_kind_auto,
		PINNED: m.multiday_kind_pinned,
		FLEXIBLE: m.multiday_kind_flexible
	};

	function toggleInclude(placeId: string, include: boolean) {
		const next = new SvelteMap(placeSelections);
		if (include) {
			next.set(placeId, []);
		} else {
			next.delete(placeId);
		}
		onchange(next);
	}

	function toggleDay(placeId: string, dayIndex: number, checked: boolean) {
		const current = placeSelections.get(placeId) ?? [];
		const next = new SvelteMap(placeSelections);
		next.set(placeId, toggleDaySlot(current, dayIndex, checked));
		onchange(next);
	}
</script>

<div class="flex flex-col gap-1">
	<div class="flex items-center justify-between">
		<span class="text-xs font-medium text-zinc-700 dark:text-zinc-300">{m.optimizer_places()}</span>
		<span class="text-xs text-zinc-400 dark:text-zinc-500">
			{placeSelections.size}
			{m.multiday_places_selected_count()}
		</span>
	</div>

	<div
		class="flex max-h-72 flex-col gap-1 overflow-y-auto rounded-md border border-zinc-200 p-2 dark:border-zinc-700"
	>
		{#each places as place (place.id)}
			{@const slots = placeSelections.get(place.id)}
			{@const included = slots !== undefined}
			<div
				class="flex flex-col gap-1 border-b border-zinc-100 py-1.5 last:border-0 dark:border-zinc-800"
			>
				<label class="flex items-center gap-2 text-sm">
					<input
						type="checkbox"
						checked={included}
						{disabled}
						onchange={(e) => toggleInclude(place.id, e.currentTarget.checked)}
						class="accent-blue-600"
					/>
					<span class="truncate text-zinc-800 dark:text-zinc-200">{place.name ?? place.id}</span>
					{#if included}
						<span
							class="ml-auto shrink-0 rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
						>
							{kindLabels[placeDaySelectionKind(slots ?? [])]()}
						</span>
					{/if}
				</label>
				{#if included}
					<div class="pl-6">
						<DayCheckboxGroup
							{numDays}
							checkedIndices={checkedDayIndices(slots ?? [])}
							{disabled}
							onchange={(dayIndex, checked) => toggleDay(place.id, dayIndex, checked)}
						/>
					</div>
				{/if}
			</div>
		{/each}
	</div>

	{#if placeSelections.size < 2}
		<p class="text-xs text-zinc-400 dark:text-zinc-500">{m.multiday_min_places_hint()}</p>
	{/if}
</div>
