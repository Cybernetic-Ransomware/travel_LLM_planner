<script lang="ts">
	let {
		filterSkipped = $bindable(null),
		filterListName = $bindable(null),
		listNames = []
	}: {
		filterSkipped?: boolean | null;
		filterListName?: string | null;
		listNames?: string[];
	} = $props();

	function onSkippedChange(event: Event): void {
		const value = (event.currentTarget as HTMLSelectElement).value;
		filterSkipped = value === '' ? null : value === 'true';
	}

	function onListNameChange(event: Event): void {
		const value = (event.currentTarget as HTMLSelectElement).value;
		filterListName = value === '' ? null : value;
	}
</script>

<div class="flex flex-wrap items-center gap-3">
	<select
		class="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm"
		value={filterSkipped === null ? '' : String(filterSkipped)}
		onchange={onSkippedChange}
	>
		<option value="">All places</option>
		<option value="false">Active only</option>
		<option value="true">Skipped only</option>
	</select>
	<select
		class="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm"
		value={filterListName ?? ''}
		onchange={onListNameChange}
	>
		<option value="">All lists</option>
		{#each listNames as name (name)}
			<option value={name}>{name}</option>
		{/each}
	</select>
</div>
