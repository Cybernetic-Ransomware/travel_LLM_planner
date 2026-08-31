<script lang="ts">
	import type { TripRevisionSummaryOut } from '$lib/types/index.js';
	import { formatDateTime } from '$lib/utils/format.js';
	import * as m from '$lib/paraglide/messages.js';
	import RestoreRevisionDialog from './RestoreRevisionDialog.svelte';
	import RevisionDetail from './RevisionDetail.svelte';

	let {
		tripId,
		currentRevision,
		revisions
	}: {
		tripId: string;
		currentRevision: number;
		revisions: TripRevisionSummaryOut[];
	} = $props();

	let restoreTarget = $state<number | null>(null);
	let restoreOpen = $state(false);
	let viewTarget = $state<number | null>(null);
	let viewOpen = $state(false);

	const SOURCE_LABEL: Record<string, () => string> = {
		CREATED: m.revision_source_created,
		MANUAL: m.revision_source_manual,
		ORCHESTRATOR: m.revision_source_orchestrator,
		REVERT: m.revision_source_revert,
		MIGRATION: m.revision_source_migration
	};

	function openView(revision: number) {
		viewTarget = revision;
		viewOpen = true;
	}
	function openRestore(revision: number) {
		restoreTarget = revision;
		restoreOpen = true;
	}
</script>

<section
	class="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
	data-testid="revision-history"
>
	<p class="mb-3 text-xs font-semibold tracking-wide text-zinc-400 uppercase dark:text-zinc-500">
		{m.revision_history_title()}
	</p>

	<ol class="flex flex-col gap-2">
		{#each revisions as rev (rev.revision)}
			{@const isCurrent = rev.revision === currentRevision}
			<li
				class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-zinc-100 pb-2 text-sm last:border-b-0 last:pb-0 dark:border-zinc-800"
			>
				<div class="flex min-w-0 flex-col">
					<span class="font-medium text-zinc-900 dark:text-zinc-100">
						#{rev.revision}
						<span
							class="ml-1 rounded bg-zinc-100 px-1.5 py-0.5 text-xs font-normal text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
						>
							{(SOURCE_LABEL[rev.source] ?? (() => rev.source))()}
						</span>
						{#if isCurrent}
							<span class="ml-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
								{m.revision_current()}
							</span>
						{/if}
					</span>
					<span class="text-xs text-zinc-500 dark:text-zinc-400">
						{formatDateTime(rev.recorded_at)} · {rev.summary}
					</span>
					{#if rev.restored_from_revision !== null && rev.restored_from_revision !== undefined}
						<span class="text-xs text-zinc-400 dark:text-zinc-500">
							↩ {m.revision_reverted_from({ revision: rev.restored_from_revision })}
						</span>
					{/if}
				</div>
				<div class="flex shrink-0 gap-1">
					<button
						class="rounded px-2 py-1 text-xs font-medium text-zinc-600 ring-1 ring-zinc-300 hover:bg-zinc-50 dark:text-zinc-300 dark:ring-zinc-600 dark:hover:bg-zinc-800"
						onclick={() => openView(rev.revision)}
					>
						{m.revision_view()}
					</button>
					{#if !isCurrent}
						<button
							class="rounded px-2 py-1 text-xs font-medium text-amber-700 ring-1 ring-amber-300 hover:bg-amber-50 dark:text-amber-300 dark:ring-amber-700 dark:hover:bg-amber-950"
							onclick={() => openRestore(rev.revision)}
							data-testid="restore-{rev.revision}"
						>
							{m.revision_restore()}
						</button>
					{/if}
				</div>
			</li>
		{/each}
	</ol>
</section>

{#if viewTarget !== null}
	<RevisionDetail bind:open={viewOpen} {tripId} revision={viewTarget} />
{/if}
{#if restoreTarget !== null}
	<RestoreRevisionDialog
		bind:open={restoreOpen}
		{tripId}
		targetRevision={restoreTarget}
		{currentRevision}
	/>
{/if}
