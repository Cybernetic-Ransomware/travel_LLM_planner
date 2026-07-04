<script lang="ts">
	import { page } from '$app/state';
	import * as m from '$lib/paraglide/messages.js';

	let {
		open = false,
		onclose
	}: {
		open?: boolean;
		onclose?: () => void;
	} = $props();

	const links = [
		{ href: '/', label: () => m.nav_dashboard(), icon: '⌂' },
		{ href: '/places', label: () => m.nav_places(), icon: '📍' },
		{ href: '/optimizer', label: () => m.nav_optimizer(), icon: '🗺' },
		{ href: '/trip', label: () => m.nav_trip(), icon: '📅' },
		{ href: '/trips', label: () => m.nav_trips(), icon: '🗂' },
		{ href: '/health', label: () => m.nav_health(), icon: '♥' }
	] as const;

	function isActive(href: string): boolean {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname === href || page.url.pathname.startsWith(href + '/');
	}
</script>

<nav class="fixed inset-y-0 left-0 z-40 flex h-full w-56 flex-col border-r border-zinc-200 bg-white transition-transform duration-200 dark:border-zinc-800 dark:bg-zinc-900 md:static md:translate-x-0 md:transition-none {open ? 'translate-x-0' : '-translate-x-full'}">
	<div class="flex h-14 items-center border-b border-zinc-200 px-4 dark:border-zinc-800">
		<span class="text-base font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">{m.app_name()}</span>
	</div>

	<ul class="flex flex-col gap-0.5 p-2 pt-3">
		{#each links as link (link.href)}
			<li>
				<a
					href={link.href}
					onclick={onclose}
					class="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors
						{isActive(link.href)
						? 'bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100'
						: 'text-zinc-500 hover:bg-zinc-50 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100'}"
				>
					<span class="text-base leading-none">{link.icon}</span>
					{link.label()}
				</a>
			</li>
		{/each}
	</ul>
</nav>

{#if open}
	<button
		onclick={onclose}
		class="fixed inset-0 z-30 bg-black/20 md:hidden"
		aria-label="Close menu"
	></button>
{/if}
