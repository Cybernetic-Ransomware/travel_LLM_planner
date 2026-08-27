<script lang="ts">
	import * as m from '$lib/paraglide/messages.js';

	let {
		numDays,
		checkedIndices,
		disabled = false,
		onchange
	}: {
		numDays: number;
		checkedIndices: number[];
		disabled?: boolean;
		onchange: (dayIndex: number, checked: boolean) => void;
	} = $props();

	const checkedSet = $derived(new Set(checkedIndices));
	const dayIndices = $derived(Array.from({ length: numDays }, (_, i) => i));
	// Above 8 days, collapse into a disclosure with the same checkboxes (hybrid matrix/popover design).
	const useCompact = $derived(numDays > 8);
</script>

{#snippet checkboxes()}
	<div class="flex flex-wrap gap-1">
		{#each dayIndices as i (i)}
			<label
				class="flex items-center gap-1 rounded border border-zinc-200 px-1.5 py-0.5 text-xs dark:border-zinc-700"
			>
				<input
					type="checkbox"
					checked={checkedSet.has(i)}
					{disabled}
					onchange={(e) => onchange(i, e.currentTarget.checked)}
				/>
				{i + 1}
			</label>
		{/each}
	</div>
{/snippet}

{#if useCompact}
	<details class="text-xs">
		<summary class="cursor-pointer text-zinc-500 dark:text-zinc-400">
			{checkedIndices.length > 0 ? checkedIndices.map((d) => d + 1).join(', ') : m.trip_any_day()}
		</summary>
		<div class="mt-1">{@render checkboxes()}</div>
	</details>
{:else}
	{@render checkboxes()}
{/if}
