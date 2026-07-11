import type { PageServerLoad } from './$types';
import type { PlaceOut, TransportMode, TripOut } from '$lib/types/index.js';
import { backendFetch } from '$lib/server/backend.js';

export interface OptimizerPrefill {
	tripId: string;
	tripName: string;
	tripDate: string;
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
	if (tripResult && fromTripId) {
		if (tripResult.ok) {
			prefill = {
				tripId: fromTripId,
				tripName: tripResult.data.name,
				tripDate: tripResult.data.date,
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
		return {
			places: [] as PlaceOut[],
			backendError: placesResult.error,
			prefill,
			prefillFailed,
			missingPrefillPlaceCount: 0
		};
	}

	const activeIds = new Set(placesResult.data.map((p) => p.id));
	const missingPrefillPlaceCount = prefill
		? prefill.selectedPlaceIds.filter((id) => !activeIds.has(id)).length
		: 0;

	return {
		places: placesResult.data,
		backendError: null,
		prefill,
		prefillFailed,
		missingPrefillPlaceCount
	};
};
