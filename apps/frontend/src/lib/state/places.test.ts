import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PlacesState } from './places.svelte.js';
import type { PlaceOut } from '$lib/types/index.js';

vi.mock('$lib/api/gmaps.js', () => ({
	getPlaces: vi.fn(),
	patchPlace: vi.fn(),
	deletePlace: vi.fn()
}));

import { getPlaces, patchPlace, deletePlace } from '$lib/api/gmaps.js';

const mockPlace = (overrides: Partial<PlaceOut> = {}): PlaceOut => ({
	id: 'place-1',
	name: 'Wawel Castle',
	address: 'Wawel 5, Kraków',
	maps_url: null,
	lat: 50.054,
	lng: 19.936,
	gmaps_place_id: null,
	list_name: 'Kraków',
	source_list_url: null,
	scraped_at: '2024-01-01T00:00:00',
	enriched_at: '2024-01-02T00:00:00',
	opening_hours: null,
	preferred_hour_from: 9,
	preferred_hour_to: 17,
	visit_duration_min: 90,
	skipped: false,
	...overrides
});

describe('PlacesState', () => {
	let state: PlacesState;

	beforeEach(() => {
		state = new PlacesState();
		vi.clearAllMocks();
	});

	describe('load', () => {
		it('populates places on success', async () => {
			vi.mocked(getPlaces).mockResolvedValue([mockPlace()]);
			await state.load();
			expect(state.places).toHaveLength(1);
			expect(state.loading).toBe(false);
			expect(state.error).toBeNull();
		});

		it('sets error and clears loading on failure', async () => {
			vi.mocked(getPlaces).mockRejectedValue(new Error('Network error'));
			await state.load();
			expect(state.places).toHaveLength(0);
			expect(state.loading).toBe(false);
			expect(state.error).toBe('Network error');
		});
	});

	describe('filtered (derived)', () => {
		beforeEach(() => {
			state.places = [
				mockPlace({ id: '1', skipped: false, list_name: 'Kraków' }),
				mockPlace({ id: '2', skipped: true, list_name: 'Kraków' }),
				mockPlace({ id: '3', skipped: false, list_name: 'Warszawa' })
			];
		});

		it('returns all places when no filters set', () => {
			expect(state.filtered).toHaveLength(3);
		});

		it('filters by skipped=false', () => {
			state.filterSkipped = false;
			expect(state.filtered).toHaveLength(2);
			expect(state.filtered.every((p) => !p.skipped)).toBe(true);
		});

		it('filters by skipped=true', () => {
			state.filterSkipped = true;
			expect(state.filtered).toHaveLength(1);
		});

		it('filters by list_name', () => {
			state.filterListName = 'Warszawa';
			expect(state.filtered).toHaveLength(1);
			expect(state.filtered[0].id).toBe('3');
		});

		it('combines skipped and list_name filters', () => {
			state.filterSkipped = false;
			state.filterListName = 'Kraków';
			expect(state.filtered).toHaveLength(1);
			expect(state.filtered[0].id).toBe('1');
		});
	});

	describe('listNames (derived)', () => {
		it('returns sorted unique list names', () => {
			state.places = [
				mockPlace({ list_name: 'Warszawa' }),
				mockPlace({ list_name: 'Kraków' }),
				mockPlace({ list_name: 'Kraków' }),
				mockPlace({ list_name: null })
			];
			expect(state.listNames).toEqual(['Kraków', 'Warszawa']);
		});
	});

	describe('stats (derived)', () => {
		it('computes correct totals from filtered places', () => {
			state.places = [
				mockPlace({ skipped: false, enriched_at: '2024-01-01', preferred_hour_from: 9 }),
				mockPlace({ skipped: true, enriched_at: null, preferred_hour_from: null }),
				mockPlace({ skipped: false, enriched_at: '2024-01-02', preferred_hour_from: null })
			];
			expect(state.stats).toEqual({ total: 3, active: 2, enriched: 2, withHours: 1 });
		});
	});

	describe('patch', () => {
		it('applies optimistic update immediately', async () => {
			state.places = [mockPlace({ id: '1', skipped: false })];
			vi.mocked(patchPlace).mockResolvedValue(mockPlace({ id: '1', skipped: true }));

			const patchPromise = state.patch('1', { skipped: true });
			expect(state.places[0].skipped).toBe(true);

			await patchPromise;
			expect(state.places[0].skipped).toBe(true);
		});

		it('rolls back on API error', async () => {
			state.places = [mockPlace({ id: '1', skipped: false })];
			vi.mocked(patchPlace).mockRejectedValue(new Error('Server error'));

			await state.patch('1', { skipped: true });

			expect(state.places[0].skipped).toBe(false);
			expect(state.error).toBe('Server error');
		});
	});

	describe('remove', () => {
		it('removes place optimistically', async () => {
			state.places = [mockPlace({ id: '1' }), mockPlace({ id: '2' })];
			vi.mocked(deletePlace).mockResolvedValue(undefined);

			const removePromise = state.remove('1');
			expect(state.places).toHaveLength(1);

			await removePromise;
			expect(state.places[0].id).toBe('2');
		});

		it('restores places on API error', async () => {
			state.places = [mockPlace({ id: '1' }), mockPlace({ id: '2' })];
			vi.mocked(deletePlace).mockRejectedValue(new Error('Delete failed'));

			await state.remove('1');

			expect(state.places).toHaveLength(2);
			expect(state.error).toBe('Delete failed');
		});
	});
});
