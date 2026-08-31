import type { PageServerLoad } from './$types';
import type { TripOut } from '$lib/types/index.js';
import { backendFetch } from '$lib/server/backend.js';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ fetch, params, depends }) => {
	// Scoped invalidation key: a confirmation-gated chat edit calls invalidate('app:trip:<id>').
	depends(`app:trip:${params.id}`);
	const result = await backendFetch<TripOut>(fetch, `/core/trips/${params.id}`);
	if (!result.ok) {
		if (result.error.status === 404) {
			throw error(404, 'Trip not found');
		}
		return { trip: null as TripOut | null, backendError: result.error };
	}
	return { trip: result.data, backendError: null };
};
