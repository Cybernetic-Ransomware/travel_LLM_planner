<script lang="ts">
	import { untrack } from 'svelte';
	import type { PlaceOut } from '$lib/types/index.js';
	import type { AccommodationDraft } from './accommodationDraft.js';
	import { isCompleteAccommodationDraft } from './accommodationDraft.js';
	import * as m from '$lib/paraglide/messages.js';

	type LocationMode = 'place' | 'manual';

	let {
		draft,
		places,
		outOfRangeNote = false,
		disabled = false,
		onchange,
		onremove
	}: {
		draft: AccommodationDraft;
		places: PlaceOut[];
		outOfRangeNote?: boolean;
		disabled?: boolean;
		onchange: (next: AccommodationDraft) => void;
		onremove: () => void;
	} = $props();

	function matchingPlaceId(): string {
		if (draft.lat === null || draft.lng === null) return '';
		return places.find((p) => p.lat === draft.lat && p.lng === draft.lng)?.id ?? '';
	}

	let locationMode = $state<LocationMode>(
		untrack(() => (matchingPlaceId() ? 'place' : draft.lat !== null ? 'manual' : 'place'))
	);

	const selectedPlaceId = $derived(matchingPlaceId());

	function update(patch: Partial<AccommodationDraft>) {
		onchange({ ...draft, ...patch });
	}

	function handlePlaceSelect(placeId: string) {
		if (!placeId) {
			update({ lat: null, lng: null });
			return;
		}
		const place = places.find((p) => p.id === placeId);
		if (!place || place.lat === null || place.lng === null) return;
		update({ lat: place.lat, lng: place.lng, name: draft.name || (place.name ?? '') });
	}
</script>

<div
	class="flex flex-col gap-2 rounded-md border border-zinc-200 p-2 dark:border-zinc-700"
	data-testid="accommodation-row"
>
	<div class="flex items-center gap-2">
		<input
			type="text"
			placeholder={m.multiday_accommodation_name_placeholder()}
			value={draft.name}
			{disabled}
			oninput={(e) => update({ name: e.currentTarget.value })}
			class="flex-1 rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
		/>
		<button
			type="button"
			onclick={onremove}
			{disabled}
			class="shrink-0 text-xs text-red-600 hover:underline dark:text-red-400"
		>
			{m.multiday_accommodation_remove()}
		</button>
	</div>

	<div class="flex gap-1 text-xs">
		<button
			type="button"
			onclick={() => (locationMode = 'place')}
			{disabled}
			class="rounded px-2 py-0.5 {locationMode === 'place'
				? 'bg-blue-600 text-white'
				: 'text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'}"
		>
			{m.multiday_accommodation_location_mode_place()}
		</button>
		<button
			type="button"
			onclick={() => (locationMode = 'manual')}
			{disabled}
			class="rounded px-2 py-0.5 {locationMode === 'manual'
				? 'bg-blue-600 text-white'
				: 'text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'}"
		>
			{m.multiday_accommodation_location_mode_manual()}
		</button>
	</div>

	{#if locationMode === 'place'}
		<select
			value={selectedPlaceId}
			{disabled}
			onchange={(e) => handlePlaceSelect(e.currentTarget.value)}
			class="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
		>
			<option value="">{m.multiday_accommodation_pick_placeholder()}</option>
			{#each places as place (place.id)}
				<option value={place.id} disabled={place.lat === null || place.lng === null}>
					{place.name ?? place.id}{place.lat === null || place.lng === null
						? ` — ${m.multiday_accommodation_place_unavailable()}`
						: ''}
				</option>
			{/each}
		</select>
	{:else}
		<div class="grid grid-cols-2 gap-2">
			<input
				type="number"
				step="any"
				placeholder={m.multiday_accommodation_lat_placeholder()}
				value={draft.lat ?? ''}
				{disabled}
				oninput={(e) =>
					update({ lat: e.currentTarget.value === '' ? null : Number(e.currentTarget.value) })}
				class="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
			/>
			<input
				type="number"
				step="any"
				placeholder={m.multiday_accommodation_lng_placeholder()}
				value={draft.lng ?? ''}
				{disabled}
				oninput={(e) =>
					update({ lng: e.currentTarget.value === '' ? null : Number(e.currentTarget.value) })}
				class="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
			/>
		</div>
	{/if}

	<div class="grid grid-cols-2 gap-2">
		<div class="flex flex-col gap-1">
			<label for="checkin-{draft.localKey}" class="text-xs text-zinc-500 dark:text-zinc-400">
				{m.multiday_accommodation_checkin_label()}
			</label>
			<input
				id="checkin-{draft.localKey}"
				type="date"
				value={draft.check_in_date}
				{disabled}
				oninput={(e) => update({ check_in_date: e.currentTarget.value })}
				class="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
			/>
		</div>
		<div class="flex flex-col gap-1">
			<label for="checkout-{draft.localKey}" class="text-xs text-zinc-500 dark:text-zinc-400">
				{m.multiday_accommodation_checkout_label()}
			</label>
			<input
				id="checkout-{draft.localKey}"
				type="date"
				value={draft.check_out_date}
				{disabled}
				oninput={(e) => update({ check_out_date: e.currentTarget.value })}
				class="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
			/>
		</div>
	</div>

	<div class="grid grid-cols-2 gap-2">
		<div class="flex flex-col gap-1">
			<label for="checkin-from-{draft.localKey}" class="text-xs text-zinc-500 dark:text-zinc-400">
				{m.multiday_accommodation_checkin_from_label()}
			</label>
			<input
				id="checkin-from-{draft.localKey}"
				type="time"
				value={draft.check_in_from ?? ''}
				{disabled}
				oninput={(e) => update({ check_in_from: e.currentTarget.value || null })}
				class="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
			/>
		</div>
		<div class="flex flex-col gap-1">
			<label for="checkout-by-{draft.localKey}" class="text-xs text-zinc-500 dark:text-zinc-400">
				{m.multiday_accommodation_checkout_by_label()}
			</label>
			<input
				id="checkout-by-{draft.localKey}"
				type="time"
				value={draft.check_out_by ?? ''}
				{disabled}
				oninput={(e) => update({ check_out_by: e.currentTarget.value || null })}
				class="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
			/>
		</div>
	</div>

	{#if !isCompleteAccommodationDraft(draft)}
		<p class="text-xs text-amber-600 dark:text-amber-400">
			{m.multiday_accommodation_incomplete()}
		</p>
	{:else if outOfRangeNote}
		<p class="text-xs text-zinc-400 dark:text-zinc-500">
			{m.multiday_accommodation_out_of_range_note()}
		</p>
	{/if}
</div>
