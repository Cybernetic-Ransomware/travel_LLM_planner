<script lang="ts">
	import Modal from '$lib/components/ui/Modal.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	let {
		open = $bindable(false),
		placeNames = [],
		onconfirm,
		loading = false
	}: {
		open?: boolean;
		placeNames?: string[];
		onconfirm?: () => void;
		loading?: boolean;
	} = $props();
</script>

<Modal bind:open title="Delete places">
	<p class="text-sm text-zinc-600 dark:text-zinc-400">
		Are you sure you want to delete
		{#if placeNames.length === 1}
			<span class="font-medium text-zinc-900 dark:text-zinc-100">"{placeNames[0]}"</span>?
		{:else}
			<span class="font-medium text-zinc-900 dark:text-zinc-100">{placeNames.length} places</span>?
		{/if}
		This action cannot be undone.
	</p>

	{#if placeNames.length > 1}
		<ul class="mt-3 max-h-32 overflow-y-auto rounded border border-zinc-100 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-800">
			{#each placeNames as name (name)}
				<li class="py-0.5 text-xs text-zinc-700 dark:text-zinc-300">{name}</li>
			{/each}
		</ul>
	{/if}

	{#snippet footer()}
		<Button variant="secondary" onclick={() => (open = false)}>Cancel</Button>
		<Button variant="danger" {loading} onclick={onconfirm}>Delete</Button>
	{/snippet}
</Modal>
