<script lang="ts">
	import type { PlaceOut } from '../../lib/types';

	let { places = [] }: { places?: PlaceOut[] } = $props();
</script>

<div class="overflow-x-auto rounded-lg border border-gray-200 bg-white">
	<table class="min-w-full divide-y divide-gray-200 text-sm">
		<thead class="bg-gray-50 text-left text-xs tracking-wide text-gray-500 uppercase">
			<tr>
				<th class="px-4 py-2 font-medium">Name</th>
				<th class="px-4 py-2 font-medium">Address</th>
				<th class="px-4 py-2 font-medium">List</th>
				<th class="px-4 py-2 font-medium">Visit (min)</th>
				<th class="px-4 py-2 font-medium">Status</th>
			</tr>
		</thead>
		<tbody class="divide-y divide-gray-100">
			{#each places as place (place.id)}
				<tr class:opacity-60={place.skipped}>
					<td class="px-4 py-2 font-medium">
						{#if place.maps_url}
							<a
								href={place.maps_url}
								target="_blank"
								rel="noreferrer"
								class="text-blue-600 hover:underline"
							>
								{place.name ?? '—'}
							</a>
						{:else}
							{place.name ?? '—'}
						{/if}
					</td>
					<td class="px-4 py-2 text-gray-600">{place.address ?? '—'}</td>
					<td class="px-4 py-2 text-gray-600">{place.list_name ?? '—'}</td>
					<td class="px-4 py-2 text-gray-600">{place.visit_duration_min ?? '—'}</td>
					<td class="px-4 py-2">
						{#if place.skipped}
							<span class="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">Skipped</span>
						{:else}
							<span class="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">Active</span>
						{/if}
					</td>
				</tr>
			{:else}
				<tr>
					<td colspan="5" class="px-4 py-6 text-center text-gray-500">
						No places match the current filters.
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
