<script lang="ts">
	import { enrichPlaces } from '$lib/api/gmaps.js';
	import { ApiError } from '$lib/api/client.js';
	import type { EnrichResponse } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';
	import Spinner from '$lib/components/ui/Spinner.svelte';

	let {
		onenrich
	}: {
		onenrich?: (result: EnrichResponse) => void;
	} = $props();

	let limit = $state(10);
	let loading = $state(false);
	let result = $state<EnrichResponse | null>(null);
	let error = $state<string | null>(null);

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (loading) return;
		loading = true;
		result = null;
		error = null;
		try {
			result = await enrichPlaces(limit);
			onenrich?.(result);
		} catch (err) {
			error = err instanceof ApiError ? err.detail : 'Enrichment failed.';
		} finally {
			loading = false;
		}
	}
</script>

<div class="rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
	<h2 class="text-base font-semibold text-zinc-900 dark:text-zinc-100">
		{m.dashboard_enrich_title()}
	</h2>
	<p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{m.dashboard_enrich_description()}</p>

	<form class="mt-4 flex flex-col gap-3" onsubmit={handleSubmit}>
		<div class="flex flex-col gap-1">
			<div class="flex items-center justify-between">
				<label for="enrich-limit" class="text-xs font-medium text-zinc-700 dark:text-zinc-300">
					{m.dashboard_enrich_limit_label()}
				</label>
				<span class="text-xs font-semibold text-zinc-900 dark:text-zinc-100">{limit}</span>
			</div>
			<input
				id="enrich-limit"
				type="range"
				min="1"
				max="100"
				bind:value={limit}
				disabled={loading}
				class="h-2 w-full cursor-pointer accent-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
			/>
			<div class="flex justify-between text-xs text-zinc-400 dark:text-zinc-500">
				<span>1</span>
				<span>100</span>
			</div>
		</div>

		<button
			type="submit"
			data-testid="enrich-submit"
			disabled={loading}
			class="flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
		>
			{#if loading}
				<Spinner size="sm" />
			{/if}
			{m.dashboard_enrich_submit()}
		</button>
	</form>

	{#if result}
		<div
			class="mt-4 rounded-md bg-green-50 px-4 py-3 text-sm text-green-800 dark:bg-green-950 dark:text-green-300"
		>
			<span class="font-semibold">{result.scanned}</span>
			{m.dashboard_enrich_result_scanned()},
			<span class="font-semibold">{result.updated}</span>
			{m.dashboard_enrich_result_updated()}
		</div>
	{/if}

	{#if error}
		<div
			class="mt-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300"
		>
			{error}
		</div>
	{/if}
</div>
