<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE, getHealth } from '../../lib/api/client';

	let status = $state<'checking' | 'ok' | 'down'>('checking');
	let latencyMs = $state<number | null>(null);
	let detail = $state<string | null>(null);

	onMount(async () => {
		const started = performance.now();
		try {
			const res = await getHealth();
			latencyMs = Math.round(performance.now() - started);
			if (res.status === 'OK') {
				status = 'ok';
			} else {
				status = 'down';
				detail = `Unexpected status: ${res.status}`;
			}
		} catch (err) {
			status = 'down';
			detail = (err as Error).message;
		}
	});
</script>

<div class="max-w-md rounded-lg border border-gray-200 bg-white p-6">
	<dl class="space-y-3 text-sm">
		<div class="flex items-center justify-between">
			<dt class="text-gray-500">Backend</dt>
			<dd>
				{#if status === 'checking'}
					<span class="text-gray-500">Checking…</span>
				{:else if status === 'ok'}
					<span class="rounded-full bg-green-100 px-2 py-0.5 font-medium text-green-700">OK</span>
				{:else}
					<span class="rounded-full bg-red-100 px-2 py-0.5 font-medium text-red-700">unavailable</span>
				{/if}
			</dd>
		</div>
		<div class="flex items-center justify-between">
			<dt class="text-gray-500">Backend URL</dt>
			<dd class="font-mono text-xs">{API_BASE}</dd>
		</div>
		{#if latencyMs !== null}
			<div class="flex items-center justify-between">
				<dt class="text-gray-500">Latency</dt>
				<dd>{latencyMs} ms</dd>
			</div>
		{/if}
	</dl>
	{#if status === 'down'}
		<p class="mt-4 text-xs text-gray-500">
			{detail} — check that the backend is running and that its CORS configuration allows this origin
			({window.location.origin}).
		</p>
	{/if}
</div>
