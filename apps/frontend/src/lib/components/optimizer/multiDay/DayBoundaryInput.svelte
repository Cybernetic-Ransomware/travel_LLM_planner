<script lang="ts">
	import type { DayBoundaryState, DayTimeMode } from './dayConfig.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		label,
		boundary,
		isEndBoundary,
		disabled = false,
		onchange
	}: {
		label: string;
		boundary: DayBoundaryState;
		isEndBoundary: boolean;
		disabled?: boolean;
		onchange: (next: DayBoundaryState) => void;
	} = $props();

	function setMode(mode: DayTimeMode) {
		onchange({ ...boundary, mode });
	}

	function setHour(value: number) {
		onchange({ ...boundary, hour: value });
	}

	function setTime(value: string) {
		onchange({ ...boundary, time: value });
	}
</script>

<div class="flex flex-col gap-1">
	<div class="flex items-center justify-between">
		<span class="text-xs font-medium text-zinc-700 dark:text-zinc-300">{label}</span>
		<div class="flex gap-1 text-xs">
			<button
				type="button"
				onclick={() => setMode('hour')}
				{disabled}
				data-testid="boundary-mode-hour"
				class="rounded px-2 py-0.5 {boundary.mode === 'hour'
					? 'bg-blue-600 text-white'
					: 'text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'}"
			>
				{m.multiday_boundary_mode_hour()}
			</button>
			<button
				type="button"
				onclick={() => setMode('exact')}
				{disabled}
				data-testid="boundary-mode-exact"
				class="rounded px-2 py-0.5 {boundary.mode === 'exact'
					? 'bg-blue-600 text-white'
					: 'text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'}"
			>
				{m.multiday_boundary_mode_exact()}
			</button>
		</div>
	</div>
	{#if boundary.mode === 'hour'}
		<input
			type="number"
			min={isEndBoundary ? 1 : 0}
			max={isEndBoundary ? 24 : 23}
			value={boundary.hour}
			{disabled}
			oninput={(e) => setHour(Number(e.currentTarget.value))}
			class="rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
		/>
	{:else}
		<input
			type="time"
			min={isEndBoundary ? '00:01' : undefined}
			value={boundary.time ?? ''}
			{disabled}
			oninput={(e) => setTime(e.currentTarget.value)}
			class="rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
		/>
	{/if}
	{#if isEndBoundary && boundary.mode === 'exact' && boundary.time === '00:00'}
		<p class="text-xs text-red-600 dark:text-red-400">{m.multiday_error_day_end_midnight()}</p>
	{/if}
</div>
