import type { PageServerLoad } from './$types';
import type { PlaceOut, TransportMode, TripOut } from '$lib/types/index.js';
import type { MultiDayOptimizerPrefill } from '$lib/components/optimizer/multiDay/hydrateMultiDayState.js';
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
	let multiDayPrefill: MultiDayOptimizerPrefill | null = null;
	let prefillFailed = false;
	if (tripResult && fromTripId) {
		if (tripResult.ok && tripResult.data.plan_type === 'SINGLE_DAY') {
			const trip = tripResult.data;
			prefill = {
				tripId: fromTripId,
				tripName: trip.name,
				tripDate: trip.date,
				selectedPlaceIds: trip.selected_place_ids,
				transportMode: trip.transport_mode,
				dayStartHour: trip.day_start_hour,
				dayEndHour: trip.day_end_hour
			};
		} else if (tripResult.ok && tripResult.data.plan_type === 'MULTI_DAY') {
			const trip = tripResult.data;
			multiDayPrefill = {
				tripId: fromTripId,
				tripName: trip.name,
				multiDayRequest: trip.multi_day_request,
				multiDayResponse: trip.multi_day_response
			};
		} else if (!tripResult.ok) {
			prefillFailed = true;
		}
	}

	if (!placesResult.ok) {
		return {
			places: [] as PlaceOut[],
			backendError: placesResult.error,
			prefill,
			multiDayPrefill,
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
		multiDayPrefill,
		prefillFailed,
		missingPrefillPlaceCount
	};
};
