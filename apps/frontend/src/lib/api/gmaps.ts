import { apiFetch } from './client.js';
import type { PlaceOut, PlacePatch, ImportResponse, EnrichResponse } from '$lib/types/index.js';

export function getPlaces(params?: { skipped?: boolean; list_name?: string }): Promise<PlaceOut[]> {
	const query = new URLSearchParams();
	if (params?.skipped !== undefined) query.set('skipped', String(params.skipped));
	if (params?.list_name) query.set('list_name', params.list_name);
	const qs = query.size > 0 ? `?${query}` : '';
	return apiFetch<PlaceOut[]>(`/core/gmaps/places${qs}`);
}

export function getPlace(id: string): Promise<PlaceOut> {
	return apiFetch<PlaceOut>(`/core/gmaps/places/${id}`);
}

export function patchPlace(id: string, patch: PlacePatch): Promise<PlaceOut> {
	return apiFetch<PlaceOut>(`/core/gmaps/places/${id}`, {
		method: 'PATCH',
		body: JSON.stringify(patch)
	});
}

export function deletePlace(id: string): Promise<void> {
	return apiFetch<void>(`/core/gmaps/places/${id}`, { method: 'DELETE' });
}

export function importList(listUrl: string): Promise<ImportResponse> {
	return apiFetch<ImportResponse>('/core/gmaps/import', {
		method: 'POST',
		body: JSON.stringify({ list_url: listUrl }),
		timeout: 120_000
	});
}

export function enrichPlaces(limit: number): Promise<EnrichResponse> {
	return apiFetch<EnrichResponse>('/core/gmaps/enrich', {
		method: 'POST',
		body: JSON.stringify({ limit }),
		timeout: 120_000
	});
}

export function enrichPlace(id: string): Promise<PlaceOut> {
	return apiFetch<PlaceOut>(`/core/gmaps/places/${encodeURIComponent(id)}/enrich`, {
		method: 'POST',
		timeout: 120_000
	});
}
