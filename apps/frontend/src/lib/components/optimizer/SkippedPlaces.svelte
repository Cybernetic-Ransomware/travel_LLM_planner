<script lang="ts">
	import type { SkippedPlace } from '$lib/types/index.js';
	import * as m from '$lib/paraglide/messages.js';

	let { skipped }: { skipped: SkippedPlace[] } = $props();
</script>

{#if skipped.length > 0}
	<div class="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950">
		<p class="text-xs font-semibold text-amber-700 dark:text-amber-300">
			{skipped.length} {m.results_places_unit()} {m.results_skipped_label()}
		</p>
		<ul class="mt-1 flex flex-col gap-0.5">
			{#each skipped as s (s.place_id)}
				<li class="text-xs text-zinc-600 dark:text-zinc-400">
					{s.name ?? s.place_id}
					<span class="text-zinc-400 dark:text-zinc-500">— {s.reason.replace(/_/g, ' ').toLowerCase()}</span>
				</li>
			{/each}
		</ul>
	</div>
{/if}
