import type { PageServerLoad } from './$types';
import type { PlaceOut } from '$lib/types/index.js';
import { backendFetch } from '$lib/server/backend.js';

const emptyStats = { total: 0, active: 0, enriched: 0, withHours: 0 };

export const load: PageServerLoad = async ({ fetch }) => {
	const result = await backendFetch<PlaceOut[]>(fetch, '/core/gmaps/places');

	if (!result.ok) {
		return { stats: emptyStats, backendError: result.error };
	}

	const places = result.data;
	return {
		stats: {
			total: places.length,
			active: places.filter((p) => !p.skipped).length,
			enriched: places.filter((p) => p.enriched_at !== null).length,
			withHours: places.filter((p) => p.opening_hours !== null).length
		},
		backendError: null
	};
};
