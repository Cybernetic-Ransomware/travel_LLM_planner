<script lang="ts">
	import { onMount } from 'svelte';
	import type { Map as LMap, Marker, Polyline } from 'leaflet';
	import type { DayPlan, RouteStep } from '$lib/types/index.js';
	import { segmentsByKind } from '../optimizer/multiDay/routeSegments.js';

	let { activeDay }: { activeDay: DayPlan } = $props();

	let container: HTMLDivElement;
	let map: LMap | null = null;
	let markers: Marker[] = [];
	let polylines: Polyline[] = [];
	let leaflet: typeof import('leaflet') | null = null;

	function stepCoords(steps: RouteStep[]): [number, number][] {
		return steps.filter((s) => s.lat !== null && s.lng !== null).map((s) => [s.lat!, s.lng!]);
	}

	function computeCenter(day: DayPlan): [number, number] {
		const { pre, post } = segmentsByKind(day);
		const coords: [number, number][] = [
			...stepCoords(day.steps),
			...stepCoords(pre?.steps ?? []),
			...stepCoords(post?.steps ?? [])
		];
		if (day.transfer) {
			coords.push([day.transfer.origin.lat, day.transfer.origin.lng]);
			coords.push([day.transfer.destination.lat, day.transfer.destination.lng]);
		}
		if (coords.length === 0) return [52.23, 21.01];
		const lat = coords.reduce((sum, c) => sum + c[0], 0) / coords.length;
		const lng = coords.reduce((sum, c) => sum + c[1], 0) / coords.length;
		return [lat, lng];
	}

	function buildStepMarkers(L: typeof import('leaflet'), steps: RouteStep[], color: string): void {
		steps
			.filter((s) => s.lat !== null && s.lng !== null)
			.forEach((s, i) => {
				const icon = L.divIcon({
					className: '',
					html: `<div style="
						width:26px;height:26px;border-radius:50%;background:${color};
						border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,.4);
						display:flex;align-items:center;justify-content:center;
						color:white;font-size:11px;font-weight:600;
					">${i + 1}</div>`,
					iconSize: [26, 26],
					iconAnchor: [13, 13]
				});
				const marker = L.marker([s.lat!, s.lng!], { icon })
					.addTo(map!)
					.bindTooltip(
						`${i + 1}. ${s.name ?? ''}\n${s.arrival_time.slice(0, 5)} → ${s.departure_time.slice(0, 5)}`,
						{ direction: 'top', offset: [0, -8] }
					);
				markers.push(marker);
			});
	}

	// A transition day gets two independent PRE/POST polylines, never one concatenating them (a fake direct route).
	function render(L: typeof import('leaflet'), day: DayPlan): void {
		markers.forEach((marker) => marker.remove());
		markers = [];
		polylines.forEach((line) => line.remove());
		polylines = [];

		if (!day.transfer) {
			buildStepMarkers(L, day.steps, '#2563eb');
			const coords = stepCoords(day.steps);
			if (coords.length > 1) {
				polylines.push(
					L.polyline(coords, { color: '#2563eb', weight: 3, opacity: 0.7 }).addTo(map!)
				);
			}
			return;
		}

		const { pre, post } = segmentsByKind(day);

		if (pre) {
			buildStepMarkers(L, pre.steps, '#2563eb');
			const coords = stepCoords(pre.steps);
			if (coords.length > 1) {
				polylines.push(
					L.polyline(coords, { color: '#2563eb', weight: 3, opacity: 0.7 }).addTo(map!)
				);
			}
		}
		if (post) {
			buildStepMarkers(L, post.steps, '#16a34a');
			const coords = stepCoords(post.steps);
			if (coords.length > 1) {
				polylines.push(
					L.polyline(coords, { color: '#16a34a', weight: 3, opacity: 0.7 }).addTo(map!)
				);
			}
		}

		const t = day.transfer;
		polylines.push(
			L.polyline(
				[
					[t.origin.lat, t.origin.lng],
					[t.destination.lat, t.destination.lng]
				],
				{ color: '#9333ea', weight: 3, opacity: 0.85, dashArray: '6 6' }
			).addTo(map!)
		);
		const endpointIcon = (label: string) =>
			L.divIcon({
				className: '',
				html: `<div style="
					width:16px;height:16px;border-radius:50%;background:#9333ea;
					border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,.4);
				" title="${label}"></div>`,
				iconSize: [16, 16],
				iconAnchor: [8, 8]
			});
		markers.push(
			L.marker([t.origin.lat, t.origin.lng], { icon: endpointIcon(t.origin.name) })
				.addTo(map!)
				.bindTooltip(t.origin.name, { direction: 'top', offset: [0, -8] })
		);
		markers.push(
			L.marker([t.destination.lat, t.destination.lng], { icon: endpointIcon(t.destination.name) })
				.addTo(map!)
				.bindTooltip(t.destination.name, { direction: 'top', offset: [0, -8] })
		);
	}

	onMount(() => {
		let cancelled = false;
		(async () => {
			const L = await import('leaflet');
			await import('leaflet/dist/leaflet.css');
			if (cancelled) return;

			leaflet = L;
			map = L.map(container).setView(computeCenter(activeDay), 13);
			L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
				attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
			}).addTo(map);

			render(L, activeDay);
		})();

		return () => {
			cancelled = true;
			map?.remove();
		};
	});

	$effect(() => {
		if (!map || !leaflet) return;
		render(leaflet, activeDay);
		map.setView(computeCenter(activeDay), map.getZoom());
	});
</script>

<div bind:this={container} class="h-full w-full rounded-lg"></div>
