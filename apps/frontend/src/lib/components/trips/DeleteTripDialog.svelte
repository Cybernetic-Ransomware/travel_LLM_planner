<script lang="ts">
	import Modal from '$lib/components/ui/Modal.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import * as m from '$lib/paraglide/messages.js';

	let {
		open = $bindable(false),
		tripName,
		onconfirm,
		loading = false
	}: {
		open?: boolean;
		tripName: string;
		onconfirm?: () => void;
		loading?: boolean;
	} = $props();
</script>

<Modal bind:open title={m.trip_delete_title()}>
	<p class="text-sm text-zinc-600 dark:text-zinc-400">
		{m.trip_delete_confirm({ name: tripName })}
	</p>

	{#snippet footer()}
		<Button variant="secondary" onclick={() => (open = false)}>{m.trip_delete_cancel()}</Button>
		<Button variant="danger" {loading} onclick={onconfirm}>{m.trip_delete_submit()}</Button>
	{/snippet}
</Modal>
