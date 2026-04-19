<script lang="ts">
	import NavBar from './NavBar.svelte';
	import ChatDrawer from './ChatDrawer.svelte';
	import LanguageSwitcher from './LanguageSwitcher.svelte';
	import ThemeSwitcher from './ThemeSwitcher.svelte';
	import * as m from '$lib/paraglide/messages.js';
	import { setThemeContext } from '$lib/state/context.svelte.js';

	let { children }: { children: import('svelte').Snippet } = $props();

	let chatOpen = $state(false);
	const theme = setThemeContext();

	$effect(() => {
		document.documentElement.classList.toggle('dark', theme.dark);
		document.documentElement.style.colorScheme = theme.dark ? 'dark' : 'light';
	});
</script>

<div class="flex h-screen overflow-hidden bg-zinc-50 dark:bg-zinc-950">
	<NavBar />

	<div class="flex flex-1 flex-col overflow-hidden">
		<header class="flex h-14 shrink-0 items-center justify-end gap-3 border-b border-zinc-200 bg-white px-6 dark:border-zinc-800 dark:bg-zinc-900">
			<ThemeSwitcher />
			<LanguageSwitcher />
			<button
				onclick={() => (chatOpen = true)}
				class="flex items-center gap-2 rounded-md border border-zinc-200 px-3 py-1.5 text-sm font-medium text-zinc-600 transition-colors hover:border-zinc-300 hover:bg-zinc-50 hover:text-zinc-900 dark:border-zinc-700 dark:text-zinc-400 dark:hover:border-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
			>
				<span>💬</span>
				{m.nav_chat()}
			</button>
		</header>

		<main class="flex-1 overflow-auto p-6">
			{@render children()}
		</main>
	</div>

	<ChatDrawer bind:open={chatOpen} />
</div>
