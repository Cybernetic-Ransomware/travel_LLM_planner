import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import TripForm from './TripForm.svelte';
import type { PlaceOut } from '$lib/types/index.js';

const mockPlace = (id: string, name: string): PlaceOut => ({
	id,
	name,
	address: null,
	maps_url: null,
	lat: 50.0,
	lng: 20.0,
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
});

const places = [mockPlace('p1', 'Wawel'), mockPlace('p2', 'Sukiennice')];

describe('TripForm', () => {
	it('renders one day row by default', async () => {
		const { getByText } = render(TripForm, { props: { places, onsubmit: vi.fn() } });
		expect(getByText('Day 1')).toBeTruthy();
	});

	it('adds a second day when clicking Add day', async () => {
		const { getByTestId, getByText } = render(TripForm, {
			props: { places, onsubmit: vi.fn() }
		});
		await userEvent.click(getByTestId('add-day'));
		expect(getByText('Day 2')).toBeTruthy();
	});

	it('submit is disabled when no places selected', async () => {
		const { getByTestId } = render(TripForm, { props: { places, onsubmit: vi.fn() } });
		const btn = getByTestId('trip-submit').element() as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
	});

	it('submit becomes enabled after selecting a place', async () => {
		const { getByText, getByTestId } = render(TripForm, {
			props: { places, onsubmit: vi.fn() }
		});
		const checkbox = getByText('Wawel')
			.element()
			.closest('div')
			?.querySelector('input[type="checkbox"]') as HTMLInputElement;
		await userEvent.click(checkbox);
		const btn = getByTestId('trip-submit').element() as HTMLButtonElement;
		expect(btn.disabled).toBe(false);
	});

	it('calls onsubmit with days and places arrays', async () => {
		const onsubmit = vi.fn();
		const { getByText, getByTestId } = render(TripForm, { props: { places, onsubmit } });
		const checkbox = getByText('Wawel')
			.element()
			.closest('div')
			?.querySelector('input[type="checkbox"]') as HTMLInputElement;
		await userEvent.click(checkbox);
		await userEvent.click(getByTestId('trip-submit'));
		expect(onsubmit).toHaveBeenCalledOnce();
		const req = onsubmit.mock.calls[0][0];
		expect(req.days).toHaveLength(1);
		expect(req.places).toHaveLength(1);
		expect(req.places[0].place_id).toBe('p1');
		expect(req.transport_mode).toBe('WALK');
	});
});
