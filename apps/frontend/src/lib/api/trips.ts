import { apiFetch } from './client.js';
import type {
	SaveTripRequest,
	TripSummaryOut,
	TripOut,
	TripRevisionListOut,
	TripRevisionOut
} from '$lib/types/index.js';

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

export function getTripRevisions(id: string): Promise<TripRevisionListOut> {
	return apiFetch<TripRevisionListOut>(`/core/trips/${id}/revisions`);
}

export function getTripRevision(id: string, revision: number): Promise<TripRevisionOut> {
	return apiFetch<TripRevisionOut>(`/core/trips/${id}/revisions/${revision}`);
}

export function restoreTripRevision(
	id: string,
	revision: number,
	expectedRevision: number
): Promise<TripOut> {
	return apiFetch<TripOut>(`/core/trips/${id}/revisions/${revision}/restore`, {
		method: 'POST',
		body: JSON.stringify({ expected_revision: expectedRevision }),
		timeout: 30_000
	});
}
