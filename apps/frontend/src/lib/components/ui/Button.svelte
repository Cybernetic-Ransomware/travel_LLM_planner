<script lang="ts">
	import type { Snippet } from 'svelte';
	import Spinner from './Spinner.svelte';

	type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';

	let {
		variant = 'primary',
		loading = false,
		disabled = false,
		type = 'button',
		onclick,
		children
	}: {
		variant?: Variant;
		loading?: boolean;
		disabled?: boolean;
		type?: 'button' | 'submit' | 'reset';
		onclick?: () => void;
		children: Snippet;
	} = $props();

	const base =
		'inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 disabled:cursor-not-allowed disabled:opacity-50';

	const variants: Record<Variant, string> = {
		primary: 'bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300',
		secondary: 'border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700',
		danger: 'bg-red-600 text-white hover:bg-red-500',
		ghost: 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100'
	};
</script>

<button
	{type}
	{onclick}
	disabled={disabled || loading}
	class="{base} {variants[variant]}"
>
	{#if loading}
		<Spinner size="sm" />
	{/if}
	{@render children()}
</button>
