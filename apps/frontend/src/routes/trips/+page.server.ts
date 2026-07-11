import type { PageServerLoad } from './$types';
import type { TripSummaryOut } from '$lib/types/index.js';
import { backendFetch } from '$lib/server/backend.js';

export const load: PageServerLoad = async ({ fetch, url }) => {
	const deletedName = url.searchParams.get('deleted');
	const result = await backendFetch<TripSummaryOut[]>(fetch, '/core/trips');
	if (!result.ok) {
		return { trips: [] as TripSummaryOut[], backendError: result.error, deletedName };
	}
	return { trips: result.data, backendError: null, deletedName };
};
