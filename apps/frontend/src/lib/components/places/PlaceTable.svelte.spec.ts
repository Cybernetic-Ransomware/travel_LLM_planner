import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import PlaceTable from './PlaceTable.svelte';
import type { PlaceOut } from '$lib/types/index.js';

const mockPlace = (overrides: Partial<PlaceOut> = {}): PlaceOut => ({
	id: 'p1',
	name: 'Wawel Castle',
	address: 'Wawel 5, Kraków',
	maps_url: null,
	lat: 50.054,
	lng: 19.936,
	gmaps_place_id: null,
	list_name: 'Kraków',
	source_list_url: null,
	scraped_at: null,
	enriched_at: null,
	opening_hours: null,
	preferred_hour_from: null,
	preferred_hour_to: null,
	visit_duration_min: null,
	skipped: false,
	...overrides
});

describe('PlaceTable', () => {
	it('shows empty state when no places', async () => {
		const { getByText } = render(PlaceTable, {
			props: { places: [], onpatch: vi.fn(), ondelete: vi.fn() }
		});

		// Empty state is locale-aware (Polish in test env)
		expect(getByText('Nie znaleziono miejsc.')).toBeTruthy();
	});

	it('renders place rows', async () => {
		const places = [
			mockPlace({ id: 'p1', name: 'Wawel Castle' }),
			mockPlace({ id: 'p2', name: 'Cloth Hall' })
		];

		const { getByText } = render(PlaceTable, {
			props: { places, onpatch: vi.fn(), ondelete: vi.fn() }
		});

		expect(getByText('Wawel Castle')).toBeTruthy();
		expect(getByText('Cloth Hall')).toBeTruthy();
	});

	it('shows row count in footer', async () => {
		const places = [mockPlace(), mockPlace({ id: 'p2', name: 'Other' })];

		const { getByText } = render(PlaceTable, {
			props: { places, onpatch: vi.fn(), ondelete: vi.fn() }
		});

		// Footer uses locale-aware unit (Polish: "miejsc")
		expect(getByText('2 miejsc')).toBeTruthy();
	});
});
