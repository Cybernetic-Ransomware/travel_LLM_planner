import { apiFetch } from './client.js';
import type { SaveTripRequest, TripOut } from '$lib/types/index.js';

export function saveTrip(request: SaveTripRequest): Promise<TripOut> {
	return apiFetch<TripOut>('/core/trips', {
		method: 'POST',
		body: JSON.stringify(request),
		timeout: 30_000
	});
}
