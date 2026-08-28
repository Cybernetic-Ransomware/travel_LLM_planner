import type {
	MultiDayRequest,
	MultiDayResponse,
	TransportModeNoTransit
} from '$lib/types/index.js';
import type { MultiDayEditableState } from './buildMultiDayRequest.js';
import { stayToDraft } from './accommodationDraft.js';

export interface MultiDayOptimizerPrefill {
	tripId: string;
	tripName: string;
	multiDayRequest: MultiDayRequest;
	multiDayResponse: MultiDayResponse;
}

// Hydrate: the formal inverse of buildMultiDayRequest; availablePlaceIds drops preferences for places that vanished.
export function hydrateEditableState(
	request: MultiDayRequest,
	availablePlaceIds?: Set<string>
): MultiDayEditableState {
	const places = availablePlaceIds
		? request.places.filter((p) => availablePlaceIds.has(p.place_id))
		: request.places;

	return {
		days: request.days,
		placeSelections: new Map(places.map((p) => [p.place_id, p.day_preferences ?? []])),
		transportMode: request.transport_mode as TransportModeNoTransit,
		accommodations: (request.accommodations ?? []).map((stay) =>
			stayToDraft(crypto.randomUUID(), stay)
		),
		transfers: new Map((request.transfers ?? []).map((t) => [t.date, t])),
		globalStart:
			request.start_lat != null && request.start_lng != null
				? { lat: request.start_lat, lng: request.start_lng }
				: null,
		globalEnd:
			request.end_lat != null && request.end_lng != null
				? { lat: request.end_lat, lng: request.end_lng }
				: null
	};
}

export function countMissingPrefillPlaces(
	request: MultiDayRequest,
	availablePlaceIds: Set<string>
): number {
	return request.places.filter((p) => !availablePlaceIds.has(p.place_id)).length;
}
