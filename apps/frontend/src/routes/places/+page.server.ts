import type { PageServerLoad } from './$types';
import type { PlaceOut } from '$lib/types/index.js';
import { backendFetch } from '$lib/server/backend.js';

export const load: PageServerLoad = async ({ fetch, url }) => {
	const result = await backendFetch<PlaceOut[]>(fetch, '/core/gmaps/places');
	const focusPlaceId = url.searchParams.get('focus');

	if (!result.ok) {
		return { places: [] as PlaceOut[], backendError: result.error, focusPlaceId };
	}

	return { places: result.data, backendError: null, focusPlaceId };
};
