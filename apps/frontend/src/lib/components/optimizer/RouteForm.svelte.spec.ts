import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import RouteForm from './RouteForm.svelte';
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
	skipped: false
});

const places = [
	mockPlace('p1', 'Wawel'),
	mockPlace('p2', 'Sukiennice'),
	mockPlace('p3', 'Kościół Mariacki')
];

describe('RouteForm', () => {
	it('renders place list', async () => {
		const { getByText } = render(RouteForm, {
			props: { places, onsubmit: vi.fn() }
		});
		expect(getByText('Wawel')).toBeTruthy();
		expect(getByText('Sukiennice')).toBeTruthy();
	});

	it('submit is disabled with fewer than 2 selected', async () => {
		const { getByTestId } = render(RouteForm, {
			props: { places, onsubmit: vi.fn() }
		});
		const btn = getByTestId('optimize-submit').element() as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
	});

	it('select all enables submit', async () => {
		const { getByTestId } = render(RouteForm, {
			props: { places, onsubmit: vi.fn() }
		});
		await userEvent.click(getByTestId('toggle-all'));
		const btn = getByTestId('optimize-submit').element() as HTMLButtonElement;
		expect(btn.disabled).toBe(false);
	});

	it('calls onsubmit with correct payload', async () => {
		const onsubmit = vi.fn();
		const { getByTestId } = render(RouteForm, {
			props: { places, onsubmit }
		});
		await userEvent.click(getByTestId('toggle-all'));
		await userEvent.click(getByTestId('optimize-submit'));
		expect(onsubmit).toHaveBeenCalledOnce();
		const req = onsubmit.mock.calls[0][0];
		expect(req.place_ids).toHaveLength(3);
		expect(req.transport_mode).toBe('WALK');
		expect(req.day_start_hour).toBe(8);
		expect(req.day_end_hour).toBe(20);
	});

	it('shows selection count', async () => {
		const { getByText } = render(RouteForm, {
			props: { places, onsubmit: vi.fn() }
		});
		expect(getByText('0 of 3 selected')).toBeTruthy();
	});

	it('initial props flow into the submitted payload', async () => {
		const onsubmit = vi.fn();
		const { getByTestId } = render(RouteForm, {
			props: {
				places,
				selectedIds: ['p1', 'p2'],
				initialTransportMode: 'DRIVE',
				initialDayStartHour: 9,
				initialDayEndHour: 21,
				onsubmit
			}
		});
		await userEvent.click(getByTestId('optimize-submit'));
		expect(onsubmit).toHaveBeenCalledOnce();
		const req = onsubmit.mock.calls[0][0];
		expect(req.place_ids).toEqual(['p1', 'p2']);
		expect(req.transport_mode).toBe('DRIVE');
		expect(req.day_start_hour).toBe(9);
		expect(req.day_end_hour).toBe(21);
	});
});
