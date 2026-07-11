import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getTrips, getTrip, saveTrip, updateTrip, deleteTrip } from './trips.js';
import type { SaveTripRequest } from '$lib/types/index.js';

function mockFetch(body: unknown, status = 200) {
	vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

describe('trips API', () => {
	beforeEach(() => vi.restoreAllMocks());

	describe('getTrips', () => {
		it('calls GET /core/trips', async () => {
			const mockFn = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
			vi.stubGlobal('fetch', mockFn);

			await getTrips();

			expect(mockFn).toHaveBeenCalledWith('/api/proxy/core/trips', expect.any(Object));
		});

		it('returns an array of trip summaries', async () => {
			const summaries = [
				{ id: 'abc', name: 'Trip A', date: '2025-06-01', created_at: '2025-06-01T10:00:00Z' }
			];
			mockFetch(summaries);

			const result = await getTrips();

			expect(result).toEqual(summaries);
		});

		it('returns an empty array when backend returns []', async () => {
			mockFetch([]);
			expect(await getTrips()).toEqual([]);
		});

		it('throws ApiError on 500', async () => {
			mockFetch({ detail: 'Internal error' }, 500);
			await expect(getTrips()).rejects.toMatchObject({ status: 500 });
		});
	});

	describe('getTrip', () => {
		it('calls GET /core/trips/:id', async () => {
			const mockFn = vi
				.fn()
				.mockResolvedValue(new Response(JSON.stringify({ id: 'abc' }), { status: 200 }));
			vi.stubGlobal('fetch', mockFn);

			await getTrip('abc');

			expect(mockFn).toHaveBeenCalledWith('/api/proxy/core/trips/abc', expect.any(Object));
		});

		it('returns the trip detail', async () => {
			const detail = {
				id: 'abc',
				name: 'Trip A',
				date: '2025-06-01',
				created_at: '2025-06-01T10:00:00Z',
				transport_mode: 'WALK',
				day_start_hour: 9,
				day_end_hour: 21,
				selected_place_ids: ['p1', 'p2'],
				optimizer_request: {
					place_ids: ['p1', 'p2'],
					transport_mode: 'WALK',
					day_start_hour: 9,
					day_end_hour: 21
				},
				optimizer_response: {
					steps: [],
					total_travel_time_s: 0,
					total_visit_time_min: 0,
					total_wait_min: 0,
					transport_mode: 'WALK',
					skipped: []
				}
			};
			mockFetch(detail);

			expect(await getTrip('abc')).toEqual(detail);
		});

		it('throws ApiError on 404', async () => {
			mockFetch({ detail: 'Not found' }, 404);

			await expect(getTrip('missing')).rejects.toMatchObject({ status: 404 });
		});

		it('throws ApiError on 502', async () => {
			mockFetch({ detail: 'Bad gateway' }, 502);

			await expect(getTrip('abc')).rejects.toMatchObject({ status: 502 });
		});

		it('throws ApiError on 504', async () => {
			mockFetch({ detail: 'Gateway timeout' }, 504);

			await expect(getTrip('abc')).rejects.toMatchObject({ status: 504 });
		});
	});

	describe('saveTrip', () => {
		it('calls POST /core/trips with JSON body', async () => {
			const mockFn = vi
				.fn()
				.mockResolvedValue(new Response(JSON.stringify({ id: 'new' }), { status: 201 }));
			vi.stubGlobal('fetch', mockFn);

			const request: SaveTripRequest = {
				name: 'Weekend in Kraków',
				date: '2025-06-01',
				optimizer_request: {
					place_ids: ['p1', 'p2'],
					transport_mode: 'WALK',
					day_start_hour: 9,
					day_end_hour: 21
				},
				optimizer_response: {
					steps: [],
					total_travel_time_s: 0,
					total_visit_time_min: 0,
					total_wait_min: 0,
					transport_mode: 'WALK',
					skipped: []
				}
			};

			await saveTrip(request);

			expect(mockFn).toHaveBeenCalledWith(
				'/api/proxy/core/trips',
				expect.objectContaining({ method: 'POST', body: JSON.stringify(request) })
			);
		});

		it('throws ApiError on 422', async () => {
			mockFetch({ detail: 'Unprocessable entity' }, 422);
			const req: SaveTripRequest = {
				name: 'x',
				date: '2025-06-01',
				optimizer_request: {
					place_ids: ['p1', 'p2'],
					transport_mode: 'WALK',
					day_start_hour: 9,
					day_end_hour: 21
				},
				optimizer_response: {
					steps: [],
					total_travel_time_s: 0,
					total_visit_time_min: 0,
					total_wait_min: 0,
					transport_mode: 'WALK',
					skipped: []
				}
			};
			await expect(saveTrip(req)).rejects.toMatchObject({ status: 422 });
		});
	});

	describe('updateTrip', () => {
		const request: SaveTripRequest = {
			name: 'Updated name',
			date: '2025-06-02',
			optimizer_request: {
				place_ids: ['p3', 'p4'],
				transport_mode: 'WALK',
				day_start_hour: 9,
				day_end_hour: 21
			},
			optimizer_response: {
				steps: [],
				total_travel_time_s: 0,
				total_visit_time_min: 0,
				total_wait_min: 0,
				transport_mode: 'WALK',
				skipped: []
			}
		};

		it('calls PUT /core/trips/:id with JSON body', async () => {
			const mockFn = vi
				.fn()
				.mockResolvedValue(new Response(JSON.stringify({ id: 'abc' }), { status: 200 }));
			vi.stubGlobal('fetch', mockFn);

			await updateTrip('abc', request);

			expect(mockFn).toHaveBeenCalledWith(
				'/api/proxy/core/trips/abc',
				expect.objectContaining({ method: 'PUT', body: JSON.stringify(request) })
			);
		});

		it('returns the updated trip', async () => {
			const updated = { id: 'abc', name: 'Updated name', updated_at: '2025-06-02T10:00:00Z' };
			mockFetch(updated);

			expect(await updateTrip('abc', request)).toEqual(updated);
		});

		it('throws ApiError on 404', async () => {
			mockFetch({ detail: 'Not found' }, 404);

			await expect(updateTrip('missing', request)).rejects.toMatchObject({ status: 404 });
		});

		it('throws ApiError on 500', async () => {
			mockFetch({ detail: 'Internal error' }, 500);

			await expect(updateTrip('abc', request)).rejects.toMatchObject({ status: 500 });
		});
	});

	describe('deleteTrip', () => {
		it('calls DELETE /core/trips/:id', async () => {
			const mockFn = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
			vi.stubGlobal('fetch', mockFn);

			await deleteTrip('abc');

			expect(mockFn).toHaveBeenCalledWith(
				'/api/proxy/core/trips/abc',
				expect.objectContaining({ method: 'DELETE' })
			);
		});

		it('resolves to undefined on 204', async () => {
			vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

			await expect(deleteTrip('abc')).resolves.toBeUndefined();
		});

		it('throws ApiError on 404', async () => {
			mockFetch({ detail: 'Not found' }, 404);

			await expect(deleteTrip('missing')).rejects.toMatchObject({ status: 404 });
		});

		it('throws ApiError on 500', async () => {
			mockFetch({ detail: 'Internal error' }, 500);

			await expect(deleteTrip('abc')).rejects.toMatchObject({ status: 500 });
		});
	});
});
