import type { PageServerLoad } from './$types';
import type { PlaceOut } from '$lib/types/index.js';
import { backendFetch } from '$lib/server/backend.js';

export const load: PageServerLoad = async ({ fetch }) => {
	const result = await backendFetch<PlaceOut[]>(fetch, '/core/gmaps/places');

	if (!result.ok) {
		return { places: [] as PlaceOut[], backendError: result.error };
	}

	return { places: result.data, backendError: null };
};
