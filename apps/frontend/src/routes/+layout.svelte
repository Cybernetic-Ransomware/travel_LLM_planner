<script lang="ts">
	import type { Pathname } from '$app/types';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { locales, localizeHref } from '$lib/paraglide/runtime';
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import AppShell from '$lib/components/layout/AppShell.svelte';
	import { setPlacesContext, setChatContext } from '$lib/state/context.svelte.js';

	let { children } = $props();

	setPlacesContext();
	setChatContext();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<AppShell>
	{@render children()}
</AppShell>

<div style="display:none">
	{#each locales as locale (locale)}
		<a href={resolve(localizeHref(page.url.pathname, { locale }) as Pathname)}>{locale}</a>
	{/each}
</div>
