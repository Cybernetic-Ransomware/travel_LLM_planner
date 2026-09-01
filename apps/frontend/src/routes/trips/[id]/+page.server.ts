import type { PageServerLoad } from './$types';
import type { TripOut, TripRevisionListOut } from '$lib/types/index.js';
import { backendFetch } from '$lib/server/backend.js';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ fetch, params, depends }) => {
	// A chat edit or a restore calls invalidate('app:trip:<id>') — re-runs BOTH fetches below.
	depends(`app:trip:${params.id}`);

	const [tripResult, revisionsResult] = await Promise.all([
		backendFetch<TripOut>(fetch, `/core/trips/${params.id}`),
		backendFetch<TripRevisionListOut>(fetch, `/core/trips/${params.id}/revisions`)
	]);

	if (!tripResult.ok) {
		if (tripResult.error.status === 404) {
			throw error(404, 'Trip not found');
		}
		return {
			trip: null as TripOut | null,
			revisions: null as TripRevisionListOut | null,
			backendError: tripResult.error
		};
	}

	return {
		trip: tripResult.data,
		revisions: revisionsResult.ok ? revisionsResult.data : null,
		backendError: null
	};
};
