import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import PlaceDayMatrix from './PlaceDayMatrix.svelte';
import type { DaySlot, PlaceOut } from '$lib/types/index.js';

function mockPlace(id: string, name: string): PlaceOut {
	return {
		id,
		name,
		address: null,
		maps_url: null,
		lat: 50,
		lng: 20,
		gmaps_place_id: null,
		list_name: null,
		source_list_url: null,
		scraped_at: null,
		enriched_at: null,
		opening_hours: null,
		preferred_hour_from: null,
		preferred_hour_to: null,
		visit_duration_min: null,
		priority: 'normal',
		skipped: false
	};
}

const places = [mockPlace('p1', 'Wawel'), mockPlace('p2', 'Sukiennice')];

describe('PlaceDayMatrix', () => {
	it('checking a place includes it with AUTO (empty slots)', async () => {
		const onchange = vi.fn();
		const { getByText } = render(PlaceDayMatrix, {
			props: { places, numDays: 3, placeSelections: new Map(), onchange }
		});
		await userEvent.click(getByText('Wawel'));
		const next = onchange.mock.calls[0][0] as Map<string, DaySlot[]>;
		expect(next.get('p1')).toEqual([]);
	});

	it('shows the AUTO badge for an included place with no day checked', async () => {
		const { getByText } = render(PlaceDayMatrix, {
			props: { places, numDays: 3, placeSelections: new Map([['p1', []]]), onchange: vi.fn() }
		});
		expect(getByText('Automatycznie')).toBeTruthy();
	});

	it('shows the PINNED badge once exactly one day is checked', async () => {
		const { getByText } = render(PlaceDayMatrix, {
			props: {
				places,
				numDays: 3,
				placeSelections: new Map([['p1', [{ day_index: 0 }]]]),
				onchange: vi.fn()
			}
		});
		expect(getByText('Przypięte')).toBeTruthy();
	});

	it('shows the FLEXIBLE badge once two or more days are checked', async () => {
		const { getByText } = render(PlaceDayMatrix, {
			props: {
				places,
				numDays: 3,
				placeSelections: new Map([['p1', [{ day_index: 0 }, { day_index: 1 }]]]),
				onchange: vi.fn()
			}
		});
		expect(getByText('Elastyczne')).toBeTruthy();
	});

	it('unchecking a place removes it from the selections entirely', async () => {
		const onchange = vi.fn();
		const { getByText } = render(PlaceDayMatrix, {
			props: {
				places,
				numDays: 3,
				placeSelections: new Map([['p1', [{ day_index: 0 }]]]),
				onchange
			}
		});
		await userEvent.click(getByText('Wawel'));
		const next = onchange.mock.calls[0][0] as Map<string, DaySlot[]>;
		expect(next.has('p1')).toBe(false);
	});

	it('shows the minimum-places hint below 2 selections', async () => {
		const { getByText } = render(PlaceDayMatrix, {
			props: { places, numDays: 3, placeSelections: new Map([['p1', []]]), onchange: vi.fn() }
		});
		expect(getByText('Zaznacz co najmniej 2 miejsca')).toBeTruthy();
	});

	it('allows checking a 50th place but blocks a 51st', async () => {
		const manyPlaces = Array.from({ length: 51 }, (_, i) => mockPlace(`p${i}`, `Place ${i}`));
		const fiftySelected = new Map(manyPlaces.slice(0, 50).map((p) => [p.id, []]));
		const onchange = vi.fn();
		const { getByText, getByTestId } = render(PlaceDayMatrix, {
			props: { places: manyPlaces, numDays: 3, placeSelections: fiftySelected, onchange }
		});
		expect(getByText('Maksymalnie można wybrać 50 miejsc.')).toBeTruthy();

		const unselectedCheckbox = getByTestId('place-include-p50').element() as HTMLInputElement;
		expect(unselectedCheckbox.checked).toBe(false);
		expect(unselectedCheckbox.disabled).toBe(true);
	});

	it('uses a compact disclosure layout above 8 days', async () => {
		const { container } = render(PlaceDayMatrix, {
			props: { places, numDays: 10, placeSelections: new Map([['p1', []]]), onchange: vi.fn() }
		});
		expect(container.querySelector('details')).toBeTruthy();
	});
});
