import { BACKEND_URL } from '$env/static/private';
import type { PageServerLoad } from './$types';
import type { PlaceOut } from '$lib/types/index.js';

export const load: PageServerLoad = async ({ fetch }) => {
	try {
		const res = await fetch(`${BACKEND_URL}/api/v1/core/gmaps/places`);
		if (!res.ok) return { places: [] as PlaceOut[] };
		const places: PlaceOut[] = await res.json();
		return { places };
	} catch {
		return { places: [] as PlaceOut[] };
	}
};
