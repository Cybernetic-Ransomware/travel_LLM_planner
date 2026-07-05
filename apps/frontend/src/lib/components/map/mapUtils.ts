import type { PlaceOut, RouteStep } from '$lib/types/index.js';

export function getMapCenter(places: PlaceOut[], steps: RouteStep[]): [number, number] {
	const source =
		steps.length > 0
			? steps.filter((s) => s.lat !== null && s.lng !== null)
			: places.filter((p) => p.lat !== null && p.lng !== null);
	if (source.length === 0) return [52.23, 21.01];
	const lat = source.reduce((sum, item) => sum + item.lat!, 0) / source.length;
	const lng = source.reduce((sum, item) => sum + item.lng!, 0) / source.length;
	return [lat, lng];
}
