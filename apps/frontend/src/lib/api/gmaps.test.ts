import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getPlaces, getPlace, patchPlace, deletePlace, importList, enrichPlaces } from './gmaps.js';

function mockFetch(body: unknown, status = 200) {
	vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

describe('gmaps API', () => {
	beforeEach(() => vi.restoreAllMocks());

	describe('getPlaces', () => {
		it('calls GET /places without query when no params', async () => {
			const mockFn = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
			vi.stubGlobal('fetch', mockFn);

			await getPlaces();

			expect(mockFn).toHaveBeenCalledWith('/api/proxy/core/gmaps/places', expect.any(Object));
		});

		it('appends skipped=true query param', async () => {
			const mockFn = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
			vi.stubGlobal('fetch', mockFn);

			await getPlaces({ skipped: true });

			expect(mockFn).toHaveBeenCalledWith(
				'/api/proxy/core/gmaps/places?skipped=true',
				expect.any(Object)
			);
		});

		it('appends list_name query param', async () => {
			const mockFn = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
			vi.stubGlobal('fetch', mockFn);

			await getPlaces({ list_name: 'Kraków' });

			expect(mockFn).toHaveBeenCalledWith(
				'/api/proxy/core/gmaps/places?list_name=Krak%C3%B3w',
				expect.any(Object)
			);
		});
	});

	describe('getPlace', () => {
		it('calls GET /places/:id', async () => {
			mockFetch({ id: 'abc' });
			const result = await getPlace('abc');
			expect(result).toEqual({ id: 'abc' });
		});
	});

	describe('patchPlace', () => {
		it('calls PATCH with JSON body', async () => {
			const mockFn = vi
				.fn()
				.mockResolvedValue(
					new Response(JSON.stringify({ id: 'abc', skipped: true }), { status: 200 })
				);
			vi.stubGlobal('fetch', mockFn);

			await patchPlace('abc', { skipped: true });

			expect(mockFn).toHaveBeenCalledWith(
				'/api/proxy/core/gmaps/places/abc',
				expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ skipped: true }) })
			);
		});
	});

	describe('deletePlace', () => {
		it('calls DELETE and returns undefined on 204', async () => {
			vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
			const result = await deletePlace('abc');
			expect(result).toBeUndefined();
		});
	});

	describe('importList', () => {
		it('calls POST /import with list_url', async () => {
			const mockFn = vi
				.fn()
				.mockResolvedValue(
					new Response(JSON.stringify({ total: 5, upserted: 3 }), { status: 200 })
				);
			vi.stubGlobal('fetch', mockFn);

			await importList('https://maps.google.com/list/abc');

			expect(mockFn).toHaveBeenCalledWith(
				'/api/proxy/core/gmaps/import',
				expect.objectContaining({
					method: 'POST',
					body: JSON.stringify({ list_url: 'https://maps.google.com/list/abc' })
				})
			);
		});
	});

	describe('enrichPlaces', () => {
		it('calls POST /enrich with limit', async () => {
			const mockFn = vi
				.fn()
				.mockResolvedValue(
					new Response(JSON.stringify({ scanned: 20, updated: 5 }), { status: 200 })
				);
			vi.stubGlobal('fetch', mockFn);

			await enrichPlaces(20);

			expect(mockFn).toHaveBeenCalledWith(
				'/api/proxy/core/gmaps/enrich',
				expect.objectContaining({ method: 'POST', body: JSON.stringify({ limit: 20 }) })
			);
		});
	});
});
