<script lang="ts">
	import { SvelteMap } from 'svelte/reactivity';
	import type { TransferBlock } from '$lib/types/index.js';
	import type { AccommodationDraft } from './accommodationDraft.js';
	import { isCompleteAccommodationDraft } from './accommodationDraft.js';
	import { computeTransitionDates } from './dayRangeReconciliation.js';
	import { isTransferBlockValid } from './transferValidation.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		transfers,
		accommodations,
		dayDates,
		disabled = false,
		onchange
	}: {
		transfers: Map<string, TransferBlock>;
		accommodations: AccommodationDraft[];
		dayDates: string[];
		disabled?: boolean;
		onchange: (next: Map<string, TransferBlock>) => void;
	} = $props();

	// Only complete drafts participate, so a half-filled accommodation row never creates a spurious transfer day.
	const transitionDates = $derived.by(() =>
		computeTransitionDates(dayDates, accommodations.filter(isCompleteAccommodationDraft))
	);

	function toggleEnabled(date: string, checked: boolean) {
		const next = new SvelteMap(transfers);
		if (checked) {
			next.set(date, { date, departure_time: '10:00', arrival_time: '11:00' });
		} else {
			next.delete(date);
		}
		onchange(next);
	}

	function update(date: string, patch: Partial<TransferBlock>) {
		const current = transfers.get(date);
		if (!current) return;
		const next = new SvelteMap(transfers);
		next.set(date, { ...current, ...patch });
		onchange(next);
	}
</script>

<div class="flex flex-col gap-2">
	<span class="text-xs font-medium text-zinc-700 dark:text-zinc-300"
		>{m.multiday_transfers_label()}</span
	>

	{#if transitionDates.length === 0}
		<p class="text-xs text-zinc-400 dark:text-zinc-500">{m.multiday_transfer_none()}</p>
	{/if}

	{#each transitionDates as date (date)}
		{@const existing = transfers.get(date)}
		{@const enabled = existing !== undefined}
		<div
			class="flex flex-col gap-2 rounded-md border border-zinc-200 p-2 dark:border-zinc-700"
			data-testid="transfer-row-{date}"
		>
			<label class="flex items-center gap-2 text-sm">
				<input
					type="checkbox"
					checked={enabled}
					{disabled}
					onchange={(e) => toggleEnabled(date, e.currentTarget.checked)}
					class="accent-blue-600"
				/>
				{m.multiday_transfer_configure_label()} — {date}
			</label>

			{#if enabled && existing}
				<div class="grid grid-cols-2 gap-2 pl-6">
					<div class="flex flex-col gap-1">
						<label for="transfer-dep-{date}" class="text-xs text-zinc-500 dark:text-zinc-400">
							{m.multiday_transfer_departure_label()}
						</label>
						<input
							id="transfer-dep-{date}"
							type="time"
							value={existing.departure_time.slice(0, 5)}
							{disabled}
							oninput={(e) => update(date, { departure_time: e.currentTarget.value })}
							class="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
						/>
					</div>
					<div class="flex flex-col gap-1">
						<label for="transfer-arr-{date}" class="text-xs text-zinc-500 dark:text-zinc-400">
							{m.multiday_transfer_arrival_label()}
						</label>
						<input
							id="transfer-arr-{date}"
							type="time"
							value={existing.arrival_time.slice(0, 5)}
							{disabled}
							oninput={(e) => update(date, { arrival_time: e.currentTarget.value })}
							class="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
						/>
					</div>
				</div>
				<input
					type="text"
					placeholder={m.multiday_transfer_label_placeholder()}
					value={existing.label ?? ''}
					{disabled}
					oninput={(e) => update(date, { label: e.currentTarget.value || null })}
					class="ml-6 rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
				/>
				{#if !isTransferBlockValid(existing)}
					<p class="pl-6 text-xs text-red-600 dark:text-red-400">{m.multiday_transfer_invalid()}</p>
				{/if}
			{/if}
		</div>
	{/each}
</div>
