<script lang="ts">
	type Size = 'sm' | 'md' | 'lg';
	let { size = 'md' }: { size?: Size } = $props();

	const sizes: Record<Size, string> = {
		sm: 'size-4',
		md: 'size-5',
		lg: 'size-8'
	};
</script>

<svg
	class="animate-spin text-current {sizes[size]}"
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	viewBox="0 0 24 24"
	aria-hidden="true"
>
	<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
	<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
</svg>
