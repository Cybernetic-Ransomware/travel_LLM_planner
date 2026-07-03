<script lang="ts">
	let { label, value, icon = '' }: { label: string; value: number; icon?: string } = $props();
</script>

<div class="rounded-lg border border-gray-200 bg-white p-4">
	<div class="flex items-center gap-2 text-sm text-gray-500">
		{#if icon}<span>{icon}</span>{/if}
		<span>{label}</span>
	</div>
	<div class="mt-1 text-2xl font-semibold">{value}</div>
</div>
