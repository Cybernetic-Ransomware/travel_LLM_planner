<script lang="ts">
	let {
		label,
		value,
		icon
	}: {
		label: string;
		value: number | string;
		icon?: string;
	} = $props();
</script>

<div
	class="rounded-lg border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900"
>
	<div class="flex items-center gap-2">
		{#if icon}
			<span class="text-base leading-none text-zinc-400 dark:text-zinc-500">{icon}</span>
		{/if}
		<span class="text-xs font-medium tracking-wide text-zinc-500 uppercase dark:text-zinc-400"
			>{label}</span
		>
	</div>
	<p class="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{value}</p>
</div>
