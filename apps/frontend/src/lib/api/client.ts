import { authHeaders } from '$lib/auth/token.js';

const API_BASE = '/api/proxy';

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
				...authHeaders(),
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
