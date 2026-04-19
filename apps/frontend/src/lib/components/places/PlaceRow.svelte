<script lang="ts">
	import type { PlaceOut, PlacePatch } from '$lib/types/index.js';
	import { formatHour } from '$lib/utils/format.js';

	let {
		place,
		onpatch,
		ondelete
	}: {
		place: PlaceOut;
		onpatch: (patch: PlacePatch) => void;
		ondelete: () => void;
	} = $props();

	function handleHourInput(field: 'preferred_hour_from' | 'preferred_hour_to', raw: string) {
		const val = parseInt(raw, 10);
		if (!isNaN(val) && val >= 0 && val <= 23) {
			onpatch({ [field]: val });
		}
	}

	function handleDurationInput(raw: string) {
		const val = parseInt(raw, 10);
		if (!isNaN(val) && val >= 1 && val <= 480) {
			onpatch({ visit_duration_min: val });
		}
	}
</script>

<tr class="border-b border-zinc-100 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800 {place.skipped ? 'opacity-60' : ''}">
	<td class="px-3 py-2.5 text-sm font-medium text-zinc-900 dark:text-zinc-100">
		{place.name ?? '—'}
	</td>
	<td class="max-w-xs truncate px-3 py-2.5 text-sm text-zinc-500 dark:text-zinc-400">
		{place.address ?? '—'}
	</td>
	<td class="px-3 py-2.5 text-sm text-zinc-500 dark:text-zinc-400">
		{place.list_name ?? '—'}
	</td>
	<td class="px-3 py-2.5">
		<div class="flex items-center gap-1 text-xs text-zinc-600 dark:text-zinc-400">
			<input
				type="number"
				min="0"
				max="23"
				value={place.preferred_hour_from ?? ''}
				onchange={(e) => handleHourInput('preferred_hour_from', e.currentTarget.value)}
				class="w-12 rounded border border-zinc-200 px-1.5 py-0.5 text-center text-xs focus:outline-none focus:ring-1 focus:ring-zinc-400 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
				placeholder="—"
			/>
			<span class="text-zinc-400">–</span>
			<input
				type="number"
				min="0"
				max="23"
				value={place.preferred_hour_to ?? ''}
				onchange={(e) => handleHourInput('preferred_hour_to', e.currentTarget.value)}
				class="w-12 rounded border border-zinc-200 px-1.5 py-0.5 text-center text-xs focus:outline-none focus:ring-1 focus:ring-zinc-400 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
				placeholder="—"
			/>
		</div>
	</td>
	<td class="px-3 py-2.5">
		<input
			type="number"
			min="1"
			max="480"
			step="5"
			value={place.visit_duration_min ?? ''}
			onchange={(e) => handleDurationInput(e.currentTarget.value)}
			class="w-16 rounded border border-zinc-200 px-1.5 py-0.5 text-center text-xs focus:outline-none focus:ring-1 focus:ring-zinc-400 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
			placeholder="—"
		/>
	</td>
	<td class="px-3 py-2.5 text-center">
		<input
			type="checkbox"
			checked={place.skipped}
			onchange={(e) => onpatch({ skipped: e.currentTarget.checked })}
			class="rounded border-zinc-300 text-zinc-900 focus:ring-zinc-400 dark:border-zinc-600"
		/>
	</td>
	<td class="px-3 py-2.5 text-center">
		<button
			onclick={ondelete}
			class="rounded p-1 text-zinc-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950 dark:hover:text-red-400"
			aria-label="Delete place"
		>
			🗑
		</button>
	</td>
</tr>
