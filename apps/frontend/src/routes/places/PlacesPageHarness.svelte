<script lang="ts">
	import { untrack } from 'svelte';
	import { setPlacesContext } from '$lib/state/context.svelte.js';
	import Page from './+page.svelte';
	import type { ComponentProps } from 'svelte';

	let {
		data,
		initialFilterSkipped = null,
		initialFilterListName = null
	}: {
		data: ComponentProps<typeof Page>['data'];
		initialFilterSkipped?: boolean | null;
		initialFilterListName?: string | null;
	} = $props();

	const places = setPlacesContext();
	untrack(() => {
		places.filterSkipped = initialFilterSkipped;
		places.filterListName = initialFilterListName;
	});
</script>

<Page {data} />
