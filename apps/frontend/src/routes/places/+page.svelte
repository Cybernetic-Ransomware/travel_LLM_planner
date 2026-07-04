<script lang="ts">
	import { getPlacesContext } from '$lib/state/context.svelte.js';
	import * as m from '$lib/paraglide/messages.js';
	import PlaceStats from '$lib/components/places/PlaceStats.svelte';
	import PlaceFilters from '$lib/components/places/PlaceFilters.svelte';
	import PlaceTable from '$lib/components/places/PlaceTable.svelte';
	import DeleteDialog from '$lib/components/places/DeleteDialog.svelte';
	import Toast from '$lib/components/ui/Toast.svelte';

	let { data } = $props();

	const places = getPlacesContext();

	$effect(() => {
		places.places = data.places;
		places.error = data.backendError
			? `${data.backendError.message} (${data.backendError.status})`
			: null;
	});

	let deleteTarget = $state<string | null>(null);
	let deleteLoading = $state(false);
	let showMap = $state(true);

	const deleteTargetName = $derived(
		places.places.find((p) => p.id === deleteTarget)?.name ?? 'this place'
	);

	async function confirmDelete() {
		if (!deleteTarget) return;
		deleteLoading = true;
		await places.remove(deleteTarget);
		deleteLoading = false;
		deleteTarget = null;
	}

	let LeafletMap: typeof import('$lib/components/map/LeafletMap.svelte').default | null =
		$state(null);

	$effect(() => {
		if (showMap && !LeafletMap) {
			import('$lib/components/map/LeafletMap.svelte').then((m) => {
				LeafletMap = m.default;
			});
		}
	});
</script>

<div class="flex h-full flex-col gap-4">
	<div>
		<h1 class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{m.nav_places()}</h1>
		<p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{m.page_places_subtitle()}</p>
	</div>

	<PlaceStats {...places.stats} />

	<div class="flex items-center justify-between">
		<PlaceFilters
			bind:filterSkipped={places.filterSkipped}
			bind:filterListName={places.filterListName}
			listNames={places.listNames}
		/>
		<button
			onclick={() => (showMap = !showMap)}
			class="text-xs text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200"
		>
			{showMap ? m.places_hide_map() : m.places_show_map()}
		</button>
	</div>

	{#if places.error}
		<Toast message={places.error} variant="error" onclose={() => (places.error = null)} />
	{/if}

	<div class="flex min-h-0 flex-1 flex-col gap-4 md:flex-row">
		<div class="{showMap ? 'md:w-3/5' : 'w-full'} min-h-0 overflow-auto">
			<PlaceTable
				places={places.filtered}
				onpatch={(id, patch) => places.patch(id, patch)}
				ondelete={(id) => (deleteTarget = id)}
			/>
		</div>

		{#if showMap}
			<div
				class="isolate h-64 overflow-hidden rounded-lg border border-zinc-200 md:h-auto md:w-2/5 dark:border-zinc-800"
			>
				{#if LeafletMap}
					<LeafletMap places={places.filtered} />
				{:else}
					<div
						class="flex h-full items-center justify-center text-sm text-zinc-400 dark:text-zinc-500"
					>
						{m.map_loading()}
					</div>
				{/if}
			</div>
		{/if}
	</div>
</div>

<DeleteDialog
	open={deleteTarget !== null}
	placeNames={deleteTarget ? [deleteTargetName] : []}
	onconfirm={confirmDelete}
	loading={deleteLoading}
/>
