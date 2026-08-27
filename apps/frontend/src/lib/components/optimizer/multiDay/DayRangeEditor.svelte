<script lang="ts">
	import { untrack } from 'svelte';
	import type { DayConfig } from '$lib/types/index.js';
	import { reconcileDays } from './dayRangeReconciliation.js';
	import {
		hydrateBoundary,
		serializeBoundary,
		isValidBoundaryPair,
		MIN_TRIP_DAYS,
		MAX_TRIP_DAYS,
		type DayBoundaryState
	} from './dayConfig.js';
	import DayBoundaryInput from './DayBoundaryInput.svelte';
	import * as m from '$lib/paraglide/messages.js';

	let {
		days,
		disabled = false,
		onchange
	}: {
		days: DayConfig[];
		disabled?: boolean;
		onchange: (days: DayConfig[]) => void;
	} = $props();

	function localTodayString(): string {
		const d = new Date();
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
	}

	let startDate = $state(untrack(() => days[0]?.date ?? localTodayString()));
	let numDays = $state(untrack(() => Math.max(days.length, 1)));

	function handleStartDateChange(value: string) {
		startDate = value;
		onchange(reconcileDays(days, startDate, numDays));
	}

	function handleNumDaysChange(value: number) {
		if (Number.isNaN(value)) return;
		numDays = Math.min(MAX_TRIP_DAYS, Math.max(MIN_TRIP_DAYS, value));
		onchange(reconcileDays(days, startDate, numDays));
	}

	function handleBoundaryChange(index: number, field: 'start' | 'end', boundary: DayBoundaryState) {
		const serialized = serializeBoundary(boundary, field === 'end');
		const day = days[index];
		const updated: DayConfig =
			field === 'start'
				? { ...day, day_start_hour: serialized.hour, day_start_time: serialized.time }
				: { ...day, day_end_hour: serialized.hour, day_end_time: serialized.time };
		onchange(days.map((d, i) => (i === index ? updated : d)));
	}
</script>

<div class="flex flex-col gap-3">
	<div class="grid grid-cols-2 gap-2">
		<div class="flex flex-col gap-1">
			<label for="multiday-start-date" class="text-xs font-medium text-zinc-700 dark:text-zinc-300">
				{m.multiday_start_date_label()}
			</label>
			<input
				id="multiday-start-date"
				type="date"
				value={startDate}
				{disabled}
				oninput={(e) => handleStartDateChange(e.currentTarget.value)}
				class="rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
			/>
		</div>
		<div class="flex flex-col gap-1">
			<label for="multiday-num-days" class="text-xs font-medium text-zinc-700 dark:text-zinc-300">
				{m.multiday_num_days_label()}
			</label>
			<input
				id="multiday-num-days"
				type="number"
				min={MIN_TRIP_DAYS}
				max={MAX_TRIP_DAYS}
				value={numDays}
				{disabled}
				oninput={(e) => handleNumDaysChange(Number(e.currentTarget.value))}
				class="rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
			/>
		</div>
	</div>

	<div class="flex flex-col gap-2">
		{#each days as day, i (i)}
			{@const startBoundary = hydrateBoundary(day.day_start_hour ?? 9, day.day_start_time ?? null)}
			{@const endBoundary = hydrateBoundary(day.day_end_hour ?? 21, day.day_end_time ?? null)}
			{@const validation = isValidBoundaryPair(startBoundary, endBoundary)}
			<div
				class="flex flex-col gap-2 rounded-md border border-zinc-200 p-2 dark:border-zinc-700"
				data-testid="day-range-row-{i}"
			>
				<p class="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
					{m.day_label()}
					{i + 1} — {day.date}
				</p>
				<div class="grid grid-cols-2 gap-2">
					<DayBoundaryInput
						label={m.optimizer_start_hour()}
						boundary={startBoundary}
						isEndBoundary={false}
						{disabled}
						onchange={(b) => handleBoundaryChange(i, 'start', b)}
					/>
					<DayBoundaryInput
						label={m.optimizer_end_hour()}
						boundary={endBoundary}
						isEndBoundary={true}
						{disabled}
						onchange={(b) => handleBoundaryChange(i, 'end', b)}
					/>
				</div>
				{#if !validation.valid && validation.errorKey === 'day_range_invalid'}
					<p class="text-xs text-red-600 dark:text-red-400">
						{m.multiday_error_day_range_invalid()}
					</p>
				{/if}
			</div>
		{/each}
	</div>
</div>
