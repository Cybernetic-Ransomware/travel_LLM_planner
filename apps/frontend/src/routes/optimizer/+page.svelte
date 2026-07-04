<script lang="ts">
	import { untrack } from 'svelte';
	import type { PageData } from './$types.js';
	import { optimizeRoute } from '$lib/api/optimizer.js';
	import { ApiError } from '$lib/api/client.js';
	import type { OptimizeRequest, OptimizeResponse } from '$lib/types/index.js';
	import RouteForm from '$lib/components/optimizer/RouteForm.svelte';
	import RouteResults from '$lib/components/optimizer/RouteResults.svelte';
	import Toast from '$lib/components/ui/Toast.svelte';

	import * as m from '$lib/paraglide/messages.js';

	let { data }: { data: PageData } = $props();

	let selectedIds = $state<string[]>(untrack(() => data.places.map((p) => p.id)));
	let result = $state<OptimizeResponse | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);

	let LeafletMap: typeof import('$lib/components/map/LeafletMap.svelte').default | null =
		$state(null);

	$effect(() => {
		if (!LeafletMap && (data.places.length > 0 || result !== null)) {
			import('$lib/components/map/LeafletMap.svelte').then((m) => {
				LeafletMap = m.default;
			});
		}
	});

	const mapPlaces = $derived(result ? [] : data.places);
	const mapSteps = $derived(result?.steps ?? []);
	const mapSelectedIds = $derived(new Set(selectedIds));

	const placesLoadError = $derived(
		data.backendError ? `${data.backendError.message} (${data.backendError.status})` : null
	);

	async function handleSubmit(request: OptimizeRequest) {
		loading = true;
		error = null;
		result = null;
		try {
			result = await optimizeRoute(request);
		} catch (err) {
			if (err instanceof ApiError) {
				const d = err.detail.toLowerCase();
				if (err.status === 504 || d.includes('timed out')) {
					error = m.optimizer_error_timeout();
				} else if (d.includes('permission_denied') || d.includes('permission denied')) {
					error = m.optimizer_error_api_key();
				} else {
					error = err.detail;
				}
			} else {
				error = 'Optimization failed.';
			}
		} finally {
			loading = false;
		}
	}
</script>

<div class="flex h-full flex-col gap-4">
	<div>
		<h1 class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{m.page_optimizer_title()}</h1>
		<p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{m.page_optimizer_subtitle()}</p>
	</div>

	{#if placesLoadError}
		<Toast message={placesLoadError} variant="error" />
	{/if}

	{#if error}
		<Toast message={error} variant="error" onclose={() => (error = null)} />
	{/if}

	<div class="flex min-h-0 flex-1 flex-col gap-4 md:flex-row">
		<div class="flex w-full flex-col gap-4 overflow-y-auto md:w-72 md:shrink-0">
			<RouteForm
				places={data.places}
				hasLoadError={data.backendError !== null}
				bind:selectedIds
				{loading}
				onsubmit={handleSubmit}
			/>

			{#if result}
				<RouteResults {result} />
			{/if}
		</div>

		<div class="h-64 flex-1 isolate overflow-hidden rounded-lg border border-zinc-200 md:h-auto dark:border-zinc-800">
			{#if LeafletMap}
				<LeafletMap places={mapPlaces} steps={mapSteps} selectedIds={mapSelectedIds} />
			{:else}
				<div class="flex h-full items-center justify-center text-sm text-zinc-400 dark:text-zinc-500">
					{m.map_loading()}
				</div>
			{/if}
		</div>
	</div>
</div>
