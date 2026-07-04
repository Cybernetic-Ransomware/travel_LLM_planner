<script lang="ts">
	import { onMount } from 'svelte';
	import * as m from '$lib/paraglide/messages.js';

	let status = $state<'checking' | 'ok' | 'down'>('checking');
	let latencyMs = $state<number | null>(null);
	let detail = $state<string | null>(null);

	onMount(async () => {
		const started = performance.now();
		try {
			const res = await fetch('/api/health');
			latencyMs = Math.round(performance.now() - started);
			const body = (await res.json()) as { status?: string; detail?: string };
			if (res.ok && body.status === 'OK') {
				status = 'ok';
			} else {
				status = 'down';
				detail = body.detail ?? `Unexpected status: ${body.status}`;
			}
		} catch (err) {
			status = 'down';
			detail = (err as Error).message;
		}
	});
</script>

<div class="flex flex-col gap-6">
	<div>
		<h1 class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{m.nav_health()}</h1>
		<p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{m.page_health_subtitle()}</p>
	</div>

	<div
		class="max-w-md rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900"
	>
		<dl class="space-y-3 text-sm">
			<div class="flex items-center justify-between">
				<dt class="text-zinc-500 dark:text-zinc-400">{m.health_backend()}</dt>
				<dd>
					{#if status === 'checking'}
						<span class="text-zinc-500 dark:text-zinc-400">{m.health_checking()}</span>
					{:else if status === 'ok'}
						<span
							class="rounded-full bg-green-100 px-2 py-0.5 font-medium text-green-700 dark:bg-green-900 dark:text-green-300"
						>
							{m.health_ok()}
						</span>
					{:else}
						<span
							class="rounded-full bg-red-100 px-2 py-0.5 font-medium text-red-700 dark:bg-red-900 dark:text-red-300"
						>
							{m.health_down()}
						</span>
					{/if}
				</dd>
			</div>
			<div class="flex items-center justify-between">
				<dt class="text-zinc-500 dark:text-zinc-400">{m.health_endpoint()}</dt>
				<dd class="font-mono text-xs text-zinc-700 dark:text-zinc-300">/api/health</dd>
			</div>
			{#if latencyMs !== null}
				<div class="flex items-center justify-between">
					<dt class="text-zinc-500 dark:text-zinc-400">{m.health_latency()}</dt>
					<dd class="text-zinc-700 dark:text-zinc-300">{latencyMs} ms</dd>
				</div>
			{/if}
		</dl>
		{#if status === 'down'}
			<p class="mt-4 text-xs text-zinc-500 dark:text-zinc-400">
				{detail} — {m.health_hint()}
			</p>
		{/if}
	</div>
</div>
