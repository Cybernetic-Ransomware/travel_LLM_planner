<script lang="ts">
	import { getLocale, setLocale, locales } from '$lib/paraglide/runtime';

	let currentLocale = $state(getLocale());
	const activeIndex = $derived(locales.indexOf(currentLocale));

	function switchLocale(locale: string) {
		setLocale(locale);
		currentLocale = locale;
	}
</script>

<div class="relative flex items-center rounded-md border border-zinc-200 p-0.5 dark:border-zinc-700">
	<div
		class="absolute top-0.5 bottom-0.5 rounded bg-zinc-900 transition-transform duration-200 ease-in-out dark:bg-zinc-100"
		style="width: calc((100% - 4px) / {locales.length}); transform: translateX(calc({activeIndex} * 100%))"
	></div>
	{#each locales as locale (locale)}
		<button
			onclick={() => switchLocale(locale)}
			class="relative z-10 flex-1 rounded px-2 py-0.5 text-xs font-semibold transition-colors {currentLocale === locale
				? 'text-white dark:text-zinc-900'
				: 'text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200'}"
			aria-current={currentLocale === locale ? 'true' : undefined}
		>
			{locale.toUpperCase()}
		</button>
	{/each}
</div>
