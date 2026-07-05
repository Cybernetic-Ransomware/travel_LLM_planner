<script lang="ts">
	let {
		value = $bindable(''),
		options,
		placeholder,
		disabled = false
	}: {
		value?: string;
		options: { value: string; label: string }[];
		placeholder?: string;
		disabled?: boolean;
	} = $props();
</script>

<select
	bind:value
	{disabled}
	class="rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 focus:ring-2 focus:ring-zinc-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
>
	{#if placeholder}
		<option value="" disabled selected={!value}>{placeholder}</option>
	{/if}
	{#each options as option (option.value)}
		<option value={option.value}>{option.label}</option>
	{/each}
</select>
