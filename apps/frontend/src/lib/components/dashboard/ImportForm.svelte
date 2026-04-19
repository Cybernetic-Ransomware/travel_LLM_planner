<script lang="ts">
	import { importList } from '$lib/api/gmaps.js';
	import { ApiError } from '$lib/api/client.js';
	import type { ImportResponse } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';
	import Spinner from '$lib/components/ui/Spinner.svelte';

	let {
		onimport
	}: {
		onimport?: (result: ImportResponse) => void;
	} = $props();

	let url = $state('');
	let loading = $state(false);
	let result = $state<ImportResponse | null>(null);
	let error = $state<string | null>(null);

	const isValidUrl = $derived(url.trim().startsWith('http'));

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (!isValidUrl || loading) return;
		loading = true;
		result = null;
		error = null;
		try {
			result = await importList(url.trim());
			onimport?.(result);
		} catch (err) {
			error = err instanceof ApiError ? err.detail : 'Import failed.';
		} finally {
			loading = false;
		}
	}
</script>

<div class="rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
	<h2 class="text-base font-semibold text-zinc-900 dark:text-zinc-100">{m.dashboard_import_title()}</h2>
	<p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{m.dashboard_import_description()}</p>

	<form class="mt-4 flex flex-col gap-3" onsubmit={handleSubmit}>
		<div class="flex flex-col gap-1">
			<label for="import-url" class="text-xs font-medium text-zinc-700 dark:text-zinc-300">
				{m.dashboard_import_url_label()}
			</label>
			<input
				id="import-url"
				type="url"
				bind:value={url}
				placeholder={m.dashboard_import_url_placeholder()}
				disabled={loading}
				class="rounded-md border border-zinc-300 px-3 py-2 text-sm placeholder-zinc-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-zinc-50 disabled:text-zinc-400 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder-zinc-500 dark:disabled:bg-zinc-900"
			/>
		</div>

		<button
			type="submit"
			data-testid="import-submit"
			disabled={!isValidUrl || loading}
			class="flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
		>
			{#if loading}
				<Spinner size="sm" />
			{/if}
			{m.dashboard_import_submit()}
		</button>
	</form>

	{#if result}
		<div class="mt-4 rounded-md bg-green-50 px-4 py-3 text-sm text-green-800 dark:bg-green-950 dark:text-green-300">
			<span class="font-semibold">{result.total}</span>
			{m.dashboard_import_result_total()},
			<span class="font-semibold">{result.upserted}</span>
			{m.dashboard_import_result_upserted()}
			{#if result.list_name}
				— <span class="italic">{result.list_name}</span>
			{/if}
		</div>
	{/if}

	{#if error}
		<div class="mt-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{error}</div>
	{/if}
</div>
