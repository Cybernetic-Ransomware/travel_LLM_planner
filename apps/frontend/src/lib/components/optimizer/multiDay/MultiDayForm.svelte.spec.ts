import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import MultiDayForm from './MultiDayForm.svelte';
import { defaultEditableState, type MultiDayEditableState } from './buildMultiDayRequest.js';
import type { PlaceOut } from '$lib/types/index.js';

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

describe('MultiDayForm', () => {
	it('submit is disabled with fewer than 2 places selected', async () => {
		const { getByTestId } = render(MultiDayForm, {
			props: { state: defaultEditableState(), places, onchange: vi.fn(), onsubmit: vi.fn() }
		});
		const btn = getByTestId('multiday-submit').element() as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
	});

	it('submit is enabled once 2 places are included and days are valid', async () => {
		const state: MultiDayEditableState = {
			...defaultEditableState(),
			placeSelections: new Map([
				['p1', []],
				['p2', []]
			])
		};
		const { getByTestId } = render(MultiDayForm, {
			props: { state, places, onchange: vi.fn(), onsubmit: vi.fn() }
		});
		const btn = getByTestId('multiday-submit').element() as HTMLButtonElement;
		expect(btn.disabled).toBe(false);
	});

	it('an incomplete accommodation row blocks submit even with valid places/days', async () => {
		const state: MultiDayEditableState = {
			...defaultEditableState(),
			placeSelections: new Map([
				['p1', []],
				['p2', []]
			]),
			accommodations: [
				{
					localKey: 'k1',
					name: 'Hotel',
					lat: null,
					lng: null,
					check_in_date: '2026-01-01',
					check_out_date: '2026-01-02',
					check_in_from: null,
					check_out_by: null
				}
			]
		};
		const { getByTestId } = render(MultiDayForm, {
			props: { state, places, onchange: vi.fn(), onsubmit: vi.fn() }
		});
		const btn = getByTestId('multiday-submit').element() as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
	});

	it('editing a place selection calls onchange with a new state object, not a mutation', async () => {
		const onchange = vi.fn();
		const state = defaultEditableState();
		const { getByText } = render(MultiDayForm, {
			props: { state, places, onchange, onsubmit: vi.fn() }
		});
		await userEvent.click(getByText('Wawel'));
		expect(onchange).toHaveBeenCalledOnce();
		const next = onchange.mock.calls[0][0] as MultiDayEditableState;
		expect(next).not.toBe(state);
		expect(next.placeSelections.has('p1')).toBe(true);
	});

	it('calls onsubmit only when the form is valid', async () => {
		const onsubmit = vi.fn();
		const state: MultiDayEditableState = {
			...defaultEditableState(),
			placeSelections: new Map([
				['p1', []],
				['p2', []]
			])
		};
		const { getByTestId } = render(MultiDayForm, {
			props: { state, places, onchange: vi.fn(), onsubmit }
		});
		await userEvent.click(getByTestId('multiday-submit'));
		expect(onsubmit).toHaveBeenCalledOnce();
	});
});
