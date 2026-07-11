import { apiFetch } from './client.js';
import type { SaveTripRequest, TripSummaryOut, TripOut } from '$lib/types/index.js';

export function getTrips(): Promise<TripSummaryOut[]> {
	return apiFetch<TripSummaryOut[]>('/core/trips');
}

export function getTrip(id: string): Promise<TripOut> {
	return apiFetch<TripOut>(`/core/trips/${id}`);
}

export function saveTrip(request: SaveTripRequest): Promise<TripOut> {
	return apiFetch<TripOut>('/core/trips', {
		method: 'POST',
		body: JSON.stringify(request),
		timeout: 30_000
	});
}

export function updateTrip(id: string, request: SaveTripRequest): Promise<TripOut> {
	return apiFetch<TripOut>(`/core/trips/${id}`, {
		method: 'PUT',
		body: JSON.stringify(request),
		timeout: 30_000
	});
}

export function deleteTrip(id: string): Promise<void> {
	return apiFetch<void>(`/core/trips/${id}`, { method: 'DELETE' });
}
