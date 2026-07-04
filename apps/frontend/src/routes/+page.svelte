<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import * as m from '$lib/paraglide/messages.js';
	import PlaceStats from '$lib/components/places/PlaceStats.svelte';
	import ImportForm from '$lib/components/dashboard/ImportForm.svelte';
	import EnrichForm from '$lib/components/dashboard/EnrichForm.svelte';

	let { data } = $props();
</script>

<div class="flex flex-col gap-6">
	<div>
		<h1 class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{m.nav_dashboard()}</h1>
		<p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{m.page_dashboard_subtitle()}</p>
	</div>

	{#if data.backendError}
		<div
			class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
		>
			<p class="font-medium">{m.error_backend_title()}</p>
			<p class="mt-1">
				{data.backendError.message}
				<span class="text-red-500 dark:text-red-400">({data.backendError.status})</span>
			</p>
		</div>
	{/if}

	<PlaceStats {...data.stats} />

	<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
		<ImportForm onimport={() => invalidateAll()} />
		<EnrichForm onenrich={() => invalidateAll()} />
	</div>
</div>
