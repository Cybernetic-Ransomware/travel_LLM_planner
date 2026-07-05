<script lang="ts">
	import { onMount } from 'svelte';
	import type { Map as LMap, Marker, Polyline } from 'leaflet';
	import type { PlaceOut, RouteStep } from '$lib/types/index.js';

	let {
		places = [],
		steps = [],
		selectedIds = new Set<string>(),
		onmarkerclick
	}: {
		places?: PlaceOut[];
		steps?: RouteStep[];
		selectedIds?: Set<string>;
		onmarkerclick?: (id: string) => void;
	} = $props();

	let container: HTMLDivElement;
	let map: LMap | null = null;
	let markers: Marker[] = [];
	let polyline: Polyline | null = null;
	let leaflet: typeof import('leaflet') | null = null;

	function center(): [number, number] {
		const source =
			steps.length > 0
				? steps.filter((s) => s.lat !== null && s.lng !== null)
				: places.filter((p) => p.lat !== null && p.lng !== null);
		if (source.length === 0) return [52.23, 21.01];
		const lat = source.reduce((s, item) => s + item.lat!, 0) / source.length;
		const lng = source.reduce((s, item) => s + item.lng!, 0) / source.length;
		return [lat, lng];
	}

	function buildMarkers(L: typeof import('leaflet')): void {
		markers.forEach((m) => m.remove());
		markers = [];
		polyline?.remove();
		polyline = null;

		const source =
			steps.length > 0
				? steps
						.filter((s) => s.lat !== null && s.lng !== null)
						.map((s, i) => ({
							id: s.place_id,
							lat: s.lat!,
							lng: s.lng!,
							label: String(i + 1),
							tooltip: `${i + 1}. ${s.name ?? ''}\n${s.arrival_time.slice(0, 5)} → ${s.departure_time.slice(0, 5)}`
						}))
				: places
						.filter((p) => p.lat !== null && p.lng !== null)
						.map((p) => ({
							id: p.id,
							lat: p.lat!,
							lng: p.lng!,
							label: '',
							tooltip: `${p.name ?? '—'}${p.address ? '\n' + p.address : ''}`,
							skipped: p.skipped,
							selected: selectedIds.has(p.id)
						}));

		source.forEach((item) => {
			const isRoute = steps.length > 0;
			const color = isRoute
				? '#2563eb'
				: (item as { skipped?: boolean; selected?: boolean }).selected
					? '#16a34a'
					: (item as { skipped?: boolean }).skipped
						? '#9ca3af'
						: '#2563eb';

			const icon = L.divIcon({
				className: '',
				html: `<div style="
					width:${isRoute ? '26px' : '14px'};
					height:${isRoute ? '26px' : '14px'};
					border-radius:50%;
					background:${color};
					border:2px solid white;
					box-shadow:0 1px 3px rgba(0,0,0,.4);
					display:flex;align-items:center;justify-content:center;
					color:white;font-size:11px;font-weight:600;
				">${item.label}</div>`,
				iconSize: isRoute ? [26, 26] : [14, 14],
				iconAnchor: isRoute ? [13, 13] : [7, 7]
			});

			const marker = L.marker([item.lat, item.lng], { icon })
				.addTo(map!)
				.bindTooltip(item.tooltip, { direction: 'top', offset: [0, -8] });

			if (onmarkerclick) {
				marker.on('click', () => onmarkerclick!(item.id));
			}

			markers.push(marker);
		});

		if (steps.length > 1) {
			const coords = steps
				.filter((s) => s.lat !== null && s.lng !== null)
				.map((s): [number, number] => [s.lat!, s.lng!]);
			polyline = L.polyline(coords, {
				color: '#2563eb',
				weight: 2,
				opacity: 0.6,
				dashArray: '6 4'
			}).addTo(map!);
		}
	}

	onMount(() => {
		(async () => {
			const L = await import('leaflet');
			await import('leaflet/dist/leaflet.css');

			leaflet = L;
			map = L.map(container).setView(center(), places.length > 0 || steps.length > 0 ? 13 : 6);
			L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
				attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
			}).addTo(map);

			buildMarkers(L);
		})();

		return () => map?.remove();
	});

	$effect(() => {
		if (!map || !leaflet) return;
		buildMarkers(leaflet);
	});
</script>

<div bind:this={container} class="h-full w-full rounded-lg"></div>
