import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
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
	priority: 'normal',
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

	it('shows priority column header (Polish locale)', async () => {
		const { getByText } = render(PlaceTable, {
			props: { places: [mockPlace()], onpatch: vi.fn(), ondelete: vi.fn() }
		});

		expect(getByText('Priorytet')).toBeTruthy();
	});

	it('selecting a priority fires onpatch with the new value', async () => {
		const onpatch = vi.fn();
		const { getByRole } = render(PlaceTable, {
			props: { places: [mockPlace()], onpatch, ondelete: vi.fn() }
		});

		const select = getByRole('combobox');
		await userEvent.selectOptions(select, getByRole('option', { name: 'Opcjonalnie' }));

		expect(onpatch).toHaveBeenCalledWith('p1', { priority: 'optional' });
	});

	it('clearing the hour-from input fires onpatch with explicit null', async () => {
		const onpatch = vi.fn();
		const { getByRole } = render(PlaceTable, {
			props: {
				places: [mockPlace({ preferred_hour_from: 9 })],
				onpatch,
				ondelete: vi.fn()
			}
		});

		// First spinbutton in the row is the hour-from input
		const hourFrom = getByRole('spinbutton').first();
		await userEvent.fill(hourFrom, '');
		await userEvent.tab(); // change fires on blur

		expect(onpatch).toHaveBeenCalledWith('p1', { preferred_hour_from: null });
	});
});
