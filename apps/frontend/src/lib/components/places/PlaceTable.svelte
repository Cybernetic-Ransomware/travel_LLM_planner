<script lang="ts">
	import PlaceRow from './PlaceRow.svelte';
	import type { PlaceOut, PlacePatch } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		places,
		onpatch,
		ondelete
	}: {
		places: PlaceOut[];
		onpatch: (id: string, patch: PlacePatch) => void;
		ondelete: (id: string) => void;
	} = $props();
</script>

<div class="overflow-hidden rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
	{#if places.length === 0}
		<div class="px-6 py-12 text-center text-sm text-zinc-400">{m.places_empty()}</div>
	{:else}
		<div class="overflow-x-auto">
			<table class="w-full text-left">
				<thead>
					<tr class="border-b border-zinc-200 bg-zinc-50 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:bg-zinc-800 dark:text-zinc-400">
						<th class="px-3 py-2.5">{m.places_col_name()}</th>
						<th class="px-3 py-2.5">{m.places_col_address()}</th>
						<th class="px-3 py-2.5">{m.places_col_list()}</th>
						<th class="px-3 py-2.5">{m.places_col_hours()}</th>
						<th class="px-3 py-2.5">{m.places_col_duration()}</th>
						<th class="px-3 py-2.5 text-center">{m.places_col_skip()}</th>
						<th class="px-3 py-2.5 text-center">{m.places_col_del()}</th>
					</tr>
				</thead>
				<tbody>
					{#each places as place (place.id)}
						<PlaceRow
							{place}
							onpatch={(patch) => onpatch(place.id, patch)}
							ondelete={() => ondelete(place.id)}
						/>
					{/each}
				</tbody>
			</table>
		</div>
		<div class="border-t border-zinc-100 px-4 py-2 text-xs text-zinc-400 dark:border-zinc-800">
			{places.length} {m.places_footer_unit()}
		</div>
	{/if}
</div>
