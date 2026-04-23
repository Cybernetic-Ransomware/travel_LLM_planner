import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiFetch, ApiError } from './client.js';

describe('apiFetch', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
	});

	it('returns parsed JSON on 200', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				new Response(JSON.stringify({ id: '1' }), { status: 200 })
			)
		);

		const result = await apiFetch<{ id: string }>('/core/gmaps/places');
		expect(result).toEqual({ id: '1' });
	});

	it('returns undefined on 204', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

		const result = await apiFetch('/core/gmaps/places/1', { method: 'DELETE' });
		expect(result).toBeUndefined();
	});

	it('throws ApiError with detail on 4xx', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 })
			)
		);

		await expect(apiFetch('/core/gmaps/places/missing')).rejects.toMatchObject({
			name: 'ApiError',
			status: 404,
			detail: 'Not found'
		});
	});

	it('throws ApiError with statusText when body has no detail', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(new Response('{}', { status: 500, statusText: 'Internal Server Error' }))
		);

		await expect(apiFetch('/core/gmaps/places')).rejects.toMatchObject({
			status: 500,
			detail: 'Internal Server Error'
		});
	});

	it('throws ApiError(0) when fetch throws network error', async () => {
		vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

		await expect(apiFetch('/core/gmaps/places')).rejects.toMatchObject({
			status: 0,
			detail: 'Cannot connect to the backend API'
		});
	});

	it('throws ApiError(504) on abort', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockRejectedValue(Object.assign(new Error('Aborted'), { name: 'AbortError' }))
		);

		await expect(apiFetch('/core/gmaps/places')).rejects.toMatchObject({
			status: 504,
			detail: 'Request timed out'
		});
	});

	it('prepends /api/proxy to the path', async () => {
		const mockFetch = vi.fn().mockResolvedValue(
			new Response(JSON.stringify([]), { status: 200 })
		);
		vi.stubGlobal('fetch', mockFetch);

		await apiFetch('/core/gmaps/places');

		expect(mockFetch).toHaveBeenCalledWith(
			'/api/proxy/core/gmaps/places',
			expect.objectContaining({ headers: expect.any(Object) })
		);
	});
});
