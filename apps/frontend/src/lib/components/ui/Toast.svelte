<script lang="ts">
	type Variant = 'success' | 'error' | 'warning' | 'info';

	let {
		message,
		variant = 'info',
		onclose
	}: {
		message: string;
		variant?: Variant;
		onclose?: () => void;
	} = $props();

	const styles: Record<Variant, string> = {
		success:
			'bg-green-50 border-green-200 text-green-800 dark:bg-green-950 dark:border-green-800 dark:text-green-300',
		error:
			'bg-red-50 border-red-200 text-red-800 dark:bg-red-950 dark:border-red-800 dark:text-red-300',
		warning:
			'bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-950 dark:border-amber-800 dark:text-amber-300',
		info: 'bg-zinc-50 border-zinc-200 text-zinc-800 dark:bg-zinc-900 dark:border-zinc-700 dark:text-zinc-200'
	};

	const icons: Record<Variant, string> = {
		success: '✓',
		error: '✕',
		warning: '⚠',
		info: 'ℹ'
	};
</script>

<div class="flex items-start gap-3 rounded-lg border px-4 py-3 text-sm {styles[variant]}">
	<span class="mt-0.5 font-semibold">{icons[variant]}</span>
	<p class="flex-1">{message}</p>
	{#if onclose}
		<button onclick={onclose} class="opacity-60 hover:opacity-100" aria-label="Dismiss">✕</button>
	{/if}
</div>
