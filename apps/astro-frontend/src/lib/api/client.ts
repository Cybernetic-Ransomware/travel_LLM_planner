import type { PlaceOut, OptimizeRequest, OptimizeResponse } from '../types';

export const API_BASE: string = import.meta.env.PUBLIC_BACKEND_URL ?? 'http://localhost:8080';

export class ApiError extends Error {
	constructor(
		public readonly status: number,
		public readonly detail: string
	) {
		super(detail);
		this.name = 'ApiError';
	}
}

interface FetchOptions extends RequestInit {
	timeout?: number;
}

// A CORS rejection surfaces in the browser as a network-level TypeError, so it is
// indistinguishable from the backend being down — both map to ApiError(0).
export async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
	const { timeout = 30_000, ...init } = options;

	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), timeout);

	try {
		const response = await fetch(`${API_BASE}${path}`, {
			...init,
			signal: controller.signal,
			headers: {
				'Content-Type': 'application/json',
				...init.headers
			}
		});

		if (response.status === 204) return undefined as T;

		if (!response.ok) {
			const body = await response.json().catch(() => ({}));
			const detail = (body as { detail?: string }).detail ?? response.statusText;
			throw new ApiError(response.status, detail);
		}

		return response.json() as Promise<T>;
	} catch (err) {
		if (err instanceof ApiError) throw err;
		if ((err as Error).name === 'AbortError') {
			throw new ApiError(504, 'Request timed out');
		}
		throw new ApiError(0, 'Cannot connect to the backend API');
	} finally {
		clearTimeout(timer);
	}
}

// Root healthcheck lives outside the /api/v1 prefix.
export function getHealth(): Promise<{ status: string }> {
	return apiFetch<{ status: string }>('/', { timeout: 5_000 });
}

export function getPlaces(): Promise<PlaceOut[]> {
	return apiFetch<PlaceOut[]>('/api/v1/core/gmaps/places');
}

export function getActivePlaces(): Promise<PlaceOut[]> {
	return apiFetch<PlaceOut[]>('/api/v1/core/gmaps/places?skipped=false');
}

export function optimizeRoute(req: OptimizeRequest): Promise<OptimizeResponse> {
	return apiFetch<OptimizeResponse>('/api/v1/core/optimizer/route', {
		method: 'POST',
		body: JSON.stringify(req)
	});
}
