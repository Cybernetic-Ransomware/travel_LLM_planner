import type { PageServerLoad } from './$types';
import type { TripSummaryOut } from '$lib/types/index.js';
import { backendFetch } from '$lib/server/backend.js';

export const load: PageServerLoad = async ({ fetch }) => {
	const result = await backendFetch<TripSummaryOut[]>(fetch, '/core/trips');
	if (!result.ok) {
		return { trips: [] as TripSummaryOut[], backendError: result.error };
	}
	return { trips: result.data, backendError: null };
};
