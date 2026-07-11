<script lang="ts">
	import { page } from '$app/state';
	import * as m from '$lib/paraglide/messages.js';

	const heading = $derived(page.status === 404 ? m.error_page_not_found() : m.error_page_generic());
	const showTripsLink = $derived(page.url.pathname.startsWith('/trips'));
</script>

<div class="flex h-full flex-col items-center justify-center gap-4 py-16 text-center">
	<p class="text-6xl font-bold text-zinc-300 dark:text-zinc-700">{page.status}</p>
	<h1 class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{heading}</h1>
	{#if page.error?.message}
		<p class="text-sm text-zinc-400 dark:text-zinc-500">{page.error.message}</p>
	{/if}
	<div class="mt-2 flex flex-wrap items-center justify-center gap-3">
		{#if showTripsLink}
			<a
				href="/trips"
				class="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
			>
				{m.error_page_back_trips()}
			</a>
		{/if}
		<a
			href="/"
			class="inline-flex items-center gap-2 rounded-md border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
		>
			{m.error_page_home()}
		</a>
	</div>
</div>
