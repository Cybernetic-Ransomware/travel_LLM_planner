<script lang="ts">
	import { onNavigate } from '$app/navigation';
	import NavBar from './NavBar.svelte';
	import ChatDrawer from './ChatDrawer.svelte';
	import LanguageSwitcher from './LanguageSwitcher.svelte';
	import ThemeSwitcher from './ThemeSwitcher.svelte';
	import * as m from '$lib/paraglide/messages.js';
	import { setThemeContext } from '$lib/state/context.svelte.js';

	let { children }: { children: import('svelte').Snippet } = $props();

	let chatOpen = $state(false);
	let navOpen = $state(false);
	const theme = setThemeContext();

	$effect(() => {
		document.documentElement.classList.toggle('dark', theme.dark);
		document.documentElement.style.colorScheme = theme.dark ? 'dark' : 'light';
	});

	onNavigate(() => {
		navOpen = false;
	});

	function openNav() {
		navOpen = true;
		chatOpen = false;
	}

	function openChat() {
		chatOpen = true;
		navOpen = false;
	}
</script>

<div class="flex h-dvh overflow-hidden bg-zinc-50 dark:bg-zinc-950">
	<NavBar open={navOpen} onclose={() => (navOpen = false)} />

	<div class="flex flex-1 flex-col overflow-hidden">
		<header class="flex h-14 shrink-0 items-center justify-end gap-3 border-b border-zinc-200 bg-white px-4 md:px-6 dark:border-zinc-800 dark:bg-zinc-900">
			<button
				onclick={openNav}
				class="mr-auto rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 md:hidden dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
				aria-label="Open menu"
			>
				<svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
					<rect x="2" y="4" width="16" height="2" rx="1"/>
					<rect x="2" y="9" width="16" height="2" rx="1"/>
					<rect x="2" y="14" width="16" height="2" rx="1"/>
				</svg>
			</button>
			<ThemeSwitcher />
			<LanguageSwitcher />
			<button
				onclick={openChat}
				class="flex items-center gap-2 rounded-md border border-zinc-200 px-3 py-1.5 text-sm font-medium text-zinc-600 transition-colors hover:border-zinc-300 hover:bg-zinc-50 hover:text-zinc-900 dark:border-zinc-700 dark:text-zinc-400 dark:hover:border-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
			>
				<span>💬</span>
				{m.nav_chat()}
			</button>
		</header>

		<main class="flex-1 overflow-auto p-4 md:p-6">
			{@render children()}
		</main>
	</div>

	<ChatDrawer bind:open={chatOpen} />
</div>
