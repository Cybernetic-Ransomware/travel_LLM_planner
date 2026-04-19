<script lang="ts">
	import Select from '$lib/components/ui/Select.svelte';

	let {
		filterSkipped = $bindable<boolean | null>(null),
		filterListName = $bindable<string | null>(null),
		listNames = []
	}: {
		filterSkipped?: boolean | null;
		filterListName?: string | null;
		listNames?: string[];
	} = $props();

	const skippedOptions = [
		{ value: '', label: 'All places' },
		{ value: 'false', label: 'Active only' },
		{ value: 'true', label: 'Skipped only' }
	];

	let skippedRaw = $state('');
	let listNameRaw = $state('');

	$effect(() => {
		filterSkipped = skippedRaw === '' ? null : skippedRaw === 'true';
	});

	$effect(() => {
		filterListName = listNameRaw === '' ? null : listNameRaw;
	});

	const listOptions = $derived([
		{ value: '', label: 'All lists' },
		...listNames.map((n) => ({ value: n, label: n }))
	]);
</script>

<div class="flex flex-wrap items-center gap-3">
	<Select bind:value={skippedRaw} options={skippedOptions} />
	<Select bind:value={listNameRaw} options={listOptions} />
</div>
