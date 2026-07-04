import { apiFetch } from './client.js';
import type { OptimizeRequest, OptimizeResponse, MultiDayRequest, MultiDayResponse } from '$lib/types/index.js';

export function optimizeRoute(request: OptimizeRequest): Promise<OptimizeResponse> {
	return apiFetch<OptimizeResponse>('/core/optimizer/route', {
		method: 'POST',
		body: JSON.stringify(request),
		timeout: 60_000
	});
}

export function optimizeTrip(request: MultiDayRequest): Promise<MultiDayResponse> {
	return apiFetch<MultiDayResponse>('/core/optimizer/trip', {
		method: 'POST',
		body: JSON.stringify(request),
		timeout: 60_000
	});
}
