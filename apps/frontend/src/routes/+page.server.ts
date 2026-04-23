import { BACKEND_URL } from '$env/static/private';
import type { PageServerLoad } from './$types';
import type { PlaceOut } from '$lib/types/index.js';

export const load: PageServerLoad = async ({ fetch }) => {
	try {
		const res = await fetch(`${BACKEND_URL}/api/v1/core/gmaps/places`);
		if (!res.ok) return { stats: { total: 0, active: 0, enriched: 0, withHours: 0 } };
		const places: PlaceOut[] = await res.json();
		return {
			stats: {
				total: places.length,
				active: places.filter((p) => !p.skipped).length,
				enriched: places.filter((p) => p.enriched_at !== null).length,
				withHours: places.filter((p) => p.opening_hours !== null).length
			}
		};
	} catch {
		return { stats: { total: 0, active: 0, enriched: 0, withHours: 0 } };
	}
};
