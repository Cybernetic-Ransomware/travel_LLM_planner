<script lang="ts">
	import { untrack } from 'svelte';
	import type { PageData } from './$types.js';
	import Toast from '$lib/components/ui/Toast.svelte';
	import { formatDateTime } from '$lib/utils/format.js';
	import * as m from '$lib/paraglide/messages.js';

	let { data }: { data: PageData } = $props();

	let deletedToast = $state<string | null>(untrack(() => data.deletedName));
</script>

<div class="flex flex-col gap-6">
	<div>
		<h1 class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{m.page_trips_title()}</h1>
		<p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{m.page_trips_subtitle()}</p>
	</div>

	{#if deletedToast}
		<Toast
			message={m.trip_delete_success({ name: deletedToast })}
			variant="success"
			onclose={() => (deletedToast = null)}
		/>
	{/if}

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
	{:else if data.trips.length === 0}
		<div class="flex flex-col items-start gap-3">
			<p class="text-sm text-zinc-500 dark:text-zinc-400">{m.trips_empty()}</p>
			<a
				href="/optimizer"
				class="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
			>
				{m.trips_empty_cta()}
			</a>
		</div>
	{:else}
		<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{#each data.trips as trip (trip.id)}
				<a
					href="/trips/{trip.id}"
					class="flex flex-col gap-1 rounded-lg border border-zinc-200 bg-white p-4 text-sm transition-colors hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700 dark:hover:bg-zinc-800"
				>
					<span class="text-base font-semibold text-zinc-900 dark:text-zinc-100">{trip.name}</span>
					{#if trip.plan_type === 'SINGLE_DAY'}
						<span class="text-zinc-500 dark:text-zinc-400">
							{m.trip_date()}: {trip.date}
						</span>
					{:else}
						<span class="text-zinc-500 dark:text-zinc-400">
							{m.trip_date_range()}: {trip.start_date} – {trip.end_date} ({trip.num_days}
							{m.trip_days()})
						</span>
					{/if}
					<span class="text-zinc-400 dark:text-zinc-500">
						{m.trip_created_at()}: {formatDateTime(trip.created_at)}
					</span>
				</a>
			{/each}
		</div>
	{/if}
</div>
