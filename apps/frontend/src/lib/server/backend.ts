import { BACKEND_URL } from '$env/static/private';

export interface BackendLoadError {
	status: number;
	message: string;
	source: 'backend' | 'network' | 'timeout' | 'unexpected';
}

export type BackendResult<T> = { ok: true; data: T } | { ok: false; error: BackendLoadError };

interface BackendFetchOptions extends RequestInit {
	timeout?: number;
}

export async function backendFetch<T>(
	fetchFn: typeof fetch,
	path: string,
	options: BackendFetchOptions = {}
): Promise<BackendResult<T>> {
	const { timeout = 30_000, ...init } = options;
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), timeout);

	try {
		const response = await fetchFn(`${BACKEND_URL}/api/v1${path}`, {
			...init,
			signal: controller.signal,
			headers: { 'Content-Type': 'application/json', ...init.headers }
		});

		if (!response.ok) {
			const body = await response.json().catch(() => ({}));
			const message =
				(body as { detail?: string }).detail ?? response.statusText ?? 'Backend request failed';
			return { ok: false, error: { status: response.status, message, source: 'backend' } };
		}

		return { ok: true, data: (await response.json()) as T };
	} catch (err) {
		if ((err as Error).name === 'AbortError') {
			return {
				ok: false,
				error: { status: 504, message: 'Backend request timed out', source: 'timeout' }
			};
		}
		return {
			ok: false,
			error: { status: 502, message: 'Cannot connect to the backend API', source: 'network' }
		};
	} finally {
		clearTimeout(timer);
	}
}
