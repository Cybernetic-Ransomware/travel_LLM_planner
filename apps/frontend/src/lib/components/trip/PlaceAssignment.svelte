<script lang="ts">
	import type { PlaceOut, DayConfig } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		places,
		days,
		selectedIds,
		assignments,
		ontoggle,
		onassign
	}: {
		places: PlaceOut[];
		days: DayConfig[];
		selectedIds: string[];
		assignments: Record<string, number | null>;
		ontoggle: (id: string) => void;
		onassign: (placeId: string, dayIndex: number | null) => void;
	} = $props();
</script>

<div
	class="max-h-64 overflow-y-auto rounded-md border border-zinc-200 dark:border-zinc-700 dark:bg-zinc-800"
>
	{#each places as place (place.id)}
		{@const selected = selectedIds.includes(place.id)}
		<div
			class="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-700 {place.skipped
				? 'opacity-50'
				: ''}"
		>
			<input
				type="checkbox"
				checked={selected}
				onchange={() => ontoggle(place.id)}
				class="accent-blue-600"
			/>
			<span class="min-w-0 flex-1 truncate text-zinc-800 dark:text-zinc-200"
				>{place.name ?? place.id}</span
			>

			{#if selected && days.length > 1}
				<select
					value={assignments[place.id] !== undefined && assignments[place.id] !== null
						? String(assignments[place.id])
						: ''}
					onchange={(e) => {
						const v = (e.target as HTMLSelectElement).value;
						onassign(place.id, v === '' ? null : Number(v));
					}}
					class="shrink-0 rounded border border-zinc-300 px-1 py-0.5 text-xs focus:border-blue-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-700 dark:text-zinc-100"
				>
					<option value="">{m.trip_any_day()}</option>
					{#each days as day, i (i)}
						<option value={String(i)}>{m.day_label()} {i + 1} ({day.date})</option>
					{/each}
				</select>
			{/if}
		</div>
	{:else}
		<p class="px-3 py-4 text-center text-xs text-zinc-400">{m.optimizer_no_places()}</p>
	{/each}
</div>
