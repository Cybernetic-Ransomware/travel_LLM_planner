<script lang="ts">
	import type { DayPlan } from '$lib/types/index.js';
	import { segmentsByKind } from './routeSegments.js';
	import StepCard from '../StepCard.svelte';
	import { formatDurationSeconds, formatTime } from '$lib/utils/format.js';
	import { skipReasonMessage } from '$lib/utils/skippedReasons.js';
	import * as m from '$lib/paraglide/messages.js';

	let { day }: { day: DayPlan } = $props();

	const segments = $derived(segmentsByKind(day));
	const isTransitionDay = $derived(day.transfer != null);
</script>

<div
	class="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900"
>
	<p class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
		{m.day_label()}
		{day.day_index + 1} — {day.date}
	</p>

	{#if !isTransitionDay}
		{#if day.steps.length > 0}
			<div class="flex flex-col gap-2">
				{#each day.steps as step, i (step.place_id)}
					<StepCard {step} index={i} />
				{/each}
			</div>
			<p class="text-xs text-zinc-500 dark:text-zinc-400">
				{formatDurationSeconds(day.total_travel_time_s)}
				{m.results_travel_label()} · {day.total_visit_time_min} min {m.results_visits_label()} ·
				{day.total_wait_min} min {m.results_wait_label()}
			</p>
		{:else}
			<p class="text-xs text-zinc-400 dark:text-zinc-500">{m.results_no_schedule()}</p>
		{/if}
	{:else}
		<div class="flex flex-col gap-2" data-testid="pre-transfer-block">
			<p class="text-xs font-semibold text-zinc-500 dark:text-zinc-400">
				{m.multiday_pre_transfer_label()}
			</p>
			{#if segments.pre && segments.pre.steps.length > 0}
				<div class="flex flex-col gap-2">
					{#each segments.pre.steps as step, i (step.place_id)}
						<StepCard {step} index={i} />
					{/each}
				</div>
				<p class="text-xs text-zinc-500 dark:text-zinc-400">
					{formatDurationSeconds(segments.pre.total_travel_time_s)}
					{m.results_travel_label()} · {segments.pre.total_visit_time_min} min {m.results_visits_label()}
				</p>
			{:else}
				<p class="text-xs text-zinc-400 dark:text-zinc-500">{m.multiday_no_stops_side()}</p>
			{/if}
		</div>

		{#if day.transfer}
			<div
				class="rounded-md border border-blue-200 bg-blue-50 p-2 text-xs dark:border-blue-800 dark:bg-blue-950"
				data-testid="transfer-block"
			>
				<p class="font-semibold text-blue-800 dark:text-blue-300">
					{m.multiday_transfer_label()}: {day.transfer.origin.name} → {day.transfer.destination
						.name}
				</p>
				<p class="text-blue-700 dark:text-blue-400">
					{formatTime(day.transfer.departure_time)} → {formatTime(day.transfer.arrival_time)} ({formatDurationSeconds(
						day.transfer.duration_s
					)}){#if day.transfer.label}
						&nbsp;· {day.transfer.label}{/if}
				</p>
			</div>
		{/if}

		<div class="flex flex-col gap-2" data-testid="post-transfer-block">
			<p class="text-xs font-semibold text-zinc-500 dark:text-zinc-400">
				{m.multiday_post_transfer_label()}
			</p>
			{#if segments.post && segments.post.steps.length > 0}
				<div class="flex flex-col gap-2">
					{#each segments.post.steps as step, i (step.place_id)}
						<StepCard {step} index={i} />
					{/each}
				</div>
				<p class="text-xs text-zinc-500 dark:text-zinc-400">
					{formatDurationSeconds(segments.post.total_travel_time_s)}
					{m.results_travel_label()} · {segments.post.total_visit_time_min} min {m.results_visits_label()}
				</p>
			{:else}
				<p class="text-xs text-zinc-400 dark:text-zinc-500">{m.multiday_no_stops_side()}</p>
			{/if}
		</div>
	{/if}

	{#if day.skipped.length > 0}
		<div
			class="rounded-lg border border-amber-200 bg-amber-50 p-2 dark:border-amber-800 dark:bg-amber-950"
		>
			<p class="text-xs font-semibold text-amber-700 dark:text-amber-300">
				{day.skipped.length}
				{m.results_places_unit()}
				{m.results_skipped_label()}
			</p>
			<ul class="mt-1 flex flex-col gap-1">
				{#each day.skipped as s (s.place_id)}
					<li class="text-xs text-zinc-600 dark:text-zinc-400">
						<span class="font-medium">{s.name ?? s.place_id}</span> — {skipReasonMessage(s.reason)}
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>
