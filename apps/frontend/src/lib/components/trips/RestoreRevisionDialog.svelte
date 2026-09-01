<script lang="ts">
	import Modal from '$lib/components/ui/Modal.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { invalidate } from '$app/navigation';
	import { ApiError } from '$lib/api/client.js';
	import { restoreTripRevision } from '$lib/api/trips.js';
	import * as m from '$lib/paraglide/messages.js';

	let {
		open = $bindable(false),
		tripId,
		targetRevision,
		currentRevision,
		onrestored
	}: {
		open?: boolean;
		tripId: string;
		targetRevision: number;
		currentRevision: number;
		onrestored?: (newRevision: number) => void;
	} = $props();

	let loading = $state(false);
	let conflict = $state(false);
	let genericError = $state(false);

	$effect(() => {
		if (open) {
			conflict = false;
			genericError = false;
		}
	});

	async function confirm() {
		loading = true;
		conflict = false;
		genericError = false;
		try {
			const updated = await restoreTripRevision(tripId, targetRevision, currentRevision);
			await invalidate(`app:trip:${tripId}`);
			onrestored?.(updated.revision);
			open = false;
		} catch (e) {
			if (e instanceof ApiError && e.status === 409) {
				conflict = true;
			} else {
				genericError = true;
			}
		} finally {
			loading = false;
		}
	}
</script>

<Modal bind:open title={m.revision_restore_title({ revision: targetRevision })}>
	<p class="text-sm text-zinc-600 dark:text-zinc-400">
		{m.revision_restore_confirm({ revision: targetRevision })}
	</p>
	{#if conflict}
		<p
			class="mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
			data-testid="restore-conflict"
		>
			{m.revision_restore_conflict()}
		</p>
	{/if}
	{#if genericError}
		<p
			class="mt-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
		>
			{m.revision_restore_error()}
		</p>
	{/if}

	{#snippet footer()}
		<Button variant="secondary" disabled={loading} onclick={() => (open = false)}>
			{m.save_trip_cancel()}
		</Button>
		<Button {loading} onclick={confirm}>
			{m.revision_restore_submit()}
		</Button>
	{/snippet}
</Modal>
