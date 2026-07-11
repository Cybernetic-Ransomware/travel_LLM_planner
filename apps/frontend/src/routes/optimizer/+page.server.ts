import type { PageServerLoad } from './$types';
import type { PlaceOut, TransportMode, TripOut } from '$lib/types/index.js';
import { backendFetch } from '$lib/server/backend.js';

export interface OptimizerPrefill {
	tripName: string;
	selectedPlaceIds: string[];
	transportMode: TransportMode;
	dayStartHour: number;
	dayEndHour: number;
}

export const load: PageServerLoad = async ({ fetch, url }) => {
	const fromTripId = url.searchParams.get('from');

	const [placesResult, tripResult] = await Promise.all([
		backendFetch<PlaceOut[]>(fetch, '/core/gmaps/places?skipped=false'),
		fromTripId ? backendFetch<TripOut>(fetch, `/core/trips/${fromTripId}`) : Promise.resolve(null)
	]);

	let prefill: OptimizerPrefill | null = null;
	let prefillFailed = false;
	if (tripResult) {
		if (tripResult.ok) {
			prefill = {
				tripName: tripResult.data.name,
				selectedPlaceIds: tripResult.data.selected_place_ids,
				transportMode: tripResult.data.transport_mode,
				dayStartHour: tripResult.data.day_start_hour,
				dayEndHour: tripResult.data.day_end_hour
			};
		} else {
			prefillFailed = true;
		}
	}

	if (!placesResult.ok) {
		return { places: [] as PlaceOut[], backendError: placesResult.error, prefill, prefillFailed };
	}

	return { places: placesResult.data, backendError: null, prefill, prefillFailed };
};
