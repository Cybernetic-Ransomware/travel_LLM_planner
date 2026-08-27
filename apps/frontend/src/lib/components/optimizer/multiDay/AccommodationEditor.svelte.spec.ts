import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import AccommodationEditor from './AccommodationEditor.svelte';
import { emptyAccommodationDraft } from './accommodationDraft.js';
import type { AccommodationDraft } from './accommodationDraft.js';
import type { PlaceOut } from '$lib/types/index.js';

function mockPlace(id: string, name: string, lat: number | null, lng: number | null): PlaceOut {
	return {
		id,
		name,
		address: null,
		maps_url: null,
		lat,
		lng,
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

const places = [
	mockPlace('p1', 'Hotel Riverside', 50.05, 19.95),
	mockPlace('p2', 'No Coords Place', null, null)
];

describe('AccommodationEditor', () => {
	it('adding a row creates an incomplete draft with the trip start date', async () => {
		const onchange = vi.fn();
		const { getByTestId } = render(AccommodationEditor, {
			props: {
				accommodations: [],
				places,
				tripStart: '2026-03-01',
				tripEnd: '2026-03-03',
				onchange
			}
		});
		await userEvent.click(getByTestId('add-accommodation'));
		const next = onchange.mock.calls[0][0] as AccommodationDraft[];
		expect(next).toHaveLength(1);
		expect(next[0].check_in_date).toBe('2026-03-01');
		expect(next[0].lat).toBeNull();
	});

	it('disables the place-picker option for a place without coordinates', async () => {
		const draft = emptyAccommodationDraft('k1', '2026-03-01');
		const { container } = render(AccommodationEditor, {
			props: {
				accommodations: [draft],
				places,
				tripStart: '2026-03-01',
				tripEnd: '2026-03-03',
				onchange: vi.fn()
			}
		});
		const options = container.querySelectorAll('option');
		const noCoordsOption = Array.from(options).find((o) => o.value === 'p2') as HTMLOptionElement;
		expect(noCoordsOption.disabled).toBe(true);
	});

	it('shows the incomplete-row hint for a draft without coordinates', async () => {
		const draft = { ...emptyAccommodationDraft('k1', '2026-03-01'), name: 'Hotel' };
		const { getByText } = render(AccommodationEditor, {
			props: {
				accommodations: [draft],
				places,
				tripStart: '2026-03-01',
				tripEnd: '2026-03-03',
				onchange: vi.fn()
			}
		});
		expect(getByText(/wymaga nazwy i współrzędnych/)).toBeTruthy();
	});

	it('does not clamp check-in/check-out dates to the trip range and shows the informational note', async () => {
		const draft: AccommodationDraft = {
			localKey: 'k1',
			name: 'Hotel B',
			lat: 50.06,
			lng: 19.94,
			check_in_date: '2026-03-02',
			check_out_date: '2026-03-05',
			check_in_from: null,
			check_out_by: null
		};
		const { getByText, container } = render(AccommodationEditor, {
			props: {
				accommodations: [draft],
				places,
				tripStart: '2026-03-01',
				tripEnd: '2026-03-03',
				onchange: vi.fn()
			}
		});
		const checkoutInput = container.querySelector('#checkout-k1') as HTMLInputElement;
		expect(checkoutInput.value).toBe('2026-03-05');
		expect(getByText(/wykracza poza zakres dni podróży/)).toBeTruthy();
	});

	it('hydrates persisted check_in_from/check_out_by into their time inputs on reopen', async () => {
		const draft: AccommodationDraft = {
			localKey: 'k1',
			name: 'Hotel A',
			lat: 50.1,
			lng: 20.1,
			check_in_date: '2026-03-01',
			check_out_date: '2026-03-03',
			check_in_from: '14:00',
			check_out_by: '11:00'
		};
		const { container } = render(AccommodationEditor, {
			props: {
				accommodations: [draft],
				places,
				tripStart: '2026-03-01',
				tripEnd: '2026-03-03',
				onchange: vi.fn()
			}
		});
		expect((container.querySelector('#checkin-from-k1') as HTMLInputElement).value).toBe('14:00');
		expect((container.querySelector('#checkout-by-k1') as HTMLInputElement).value).toBe('11:00');
	});

	it('editing check_in_from preserves every other field on the draft (lossless)', async () => {
		const draft: AccommodationDraft = {
			localKey: 'k1',
			name: 'Hotel A',
			lat: 50.1,
			lng: 20.1,
			check_in_date: '2026-03-01',
			check_out_date: '2026-03-03',
			check_in_from: null,
			check_out_by: null
		};
		const onchange = vi.fn();
		const { container } = render(AccommodationEditor, {
			props: {
				accommodations: [draft],
				places,
				tripStart: '2026-03-01',
				tripEnd: '2026-03-03',
				onchange
			}
		});
		const input = container.querySelector('#checkin-from-k1') as HTMLInputElement;
		await userEvent.fill(input, '15:30');
		const next = onchange.mock.calls.at(-1)?.[0] as AccommodationDraft[];
		expect(next[0]).toEqual({ ...draft, check_in_from: '15:30' });
	});

	it('flags overlapping complete stays', async () => {
		const drafts: AccommodationDraft[] = [
			{
				localKey: 'a',
				name: 'A',
				lat: 1,
				lng: 1,
				check_in_date: '2026-03-01',
				check_out_date: '2026-03-05',
				check_in_from: null,
				check_out_by: null
			},
			{
				localKey: 'b',
				name: 'B',
				lat: 2,
				lng: 2,
				check_in_date: '2026-03-03',
				check_out_date: '2026-03-06',
				check_in_from: null,
				check_out_by: null
			}
		];
		const { getByText } = render(AccommodationEditor, {
			props: {
				accommodations: drafts,
				places,
				tripStart: '2026-03-01',
				tripEnd: '2026-03-06',
				onchange: vi.fn()
			}
		});
		expect(getByText(/nakładają się/)).toBeTruthy();
	});

	it('removing a row drops it from the list', async () => {
		const onchange = vi.fn();
		const draft = emptyAccommodationDraft('k1', '2026-03-01');
		const { getByText } = render(AccommodationEditor, {
			props: {
				accommodations: [draft],
				places,
				tripStart: '2026-03-01',
				tripEnd: '2026-03-03',
				onchange
			}
		});
		await userEvent.click(getByText('Usuń'));
		expect(onchange).toHaveBeenCalledWith([]);
	});
});
