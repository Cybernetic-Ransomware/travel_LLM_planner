import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import Page from './+page.svelte';
import { optimizeRoute } from '$lib/api/optimizer.js';
import { updateTrip } from '$lib/api/trips.js';
import { ApiError } from '$lib/api/client.js';
import type { OptimizeResponse, PlaceOut, TripOut } from '$lib/types/index.js';
import type { OptimizerPrefill } from './+page.server.js';

vi.mock('$lib/api/optimizer.js', () => ({
	optimizeRoute: vi.fn()
}));

vi.mock('$lib/api/trips.js', () => ({
	updateTrip: vi.fn(),
	saveTrip: vi.fn()
}));

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

const places = [mockPlace('p1', 'Wawel'), mockPlace('p2', 'Sukiennice')];

const prefill: OptimizerPrefill = {
	tripId: 'trip-1',
	tripName: 'Weekend in Kraków',
	tripDate: '2026-07-11',
	selectedPlaceIds: ['p1', 'p2'],
	transportMode: 'WALK',
	dayStartHour: 9,
	dayEndHour: 21
};

const mockResult: OptimizeResponse = {
	steps: [],
	total_travel_time_s: 1800,
	total_visit_time_min: 90,
	total_wait_min: 15,
	transport_mode: 'WALK',
	skipped: []
};

const updatedTrip: TripOut = {
	id: 'trip-1',
	name: 'Weekend in Kraków',
	date: '2026-07-11',
	created_at: '2026-07-11T10:00:00Z',
	updated_at: '2026-07-11T11:00:00Z',
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
	optimizer_response: mockResult
};

function pageData(overrides: Record<string, unknown> = {}) {
	return {
		orchestratorReady: true,
		places,
		backendError: null,
		prefill,
		prefillFailed: false,
		missingPrefillPlaceCount: 0,
		...overrides
	};
}

async function renderAndOptimize(overrides: Record<string, unknown> = {}) {
	const screen = render(Page, { props: { data: pageData(overrides) } });
	await userEvent.click(screen.getByTestId('optimize-submit'));
	return screen;
}

describe('/optimizer page — update saved trip', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(optimizeRoute).mockResolvedValue(mockResult);
		vi.mocked(updateTrip).mockResolvedValue(updatedTrip);
	});

	it('shows update and save-as-new buttons after optimizing with prefill', async () => {
		const { getByRole } = await renderAndOptimize();
		await expect.element(getByRole('button', { name: 'Zaktualizuj zapisaną trasę' })).toBeVisible();
		await expect.element(getByRole('button', { name: 'Zapisz jako nową trasę' })).toBeVisible();
	});

	it('shows only plain save button without prefill', async () => {
		const { getByRole } = await renderAndOptimize({ prefill: null });
		await expect.element(getByRole('button', { name: 'Zapisz trasę' })).toBeVisible();
		expect(getByRole('button', { name: 'Zaktualizuj zapisaną trasę' }).query()).toBeNull();
	});

	it('clicking update calls updateTrip with trip id and full payload', async () => {
		const { getByRole } = await renderAndOptimize();
		await userEvent.click(getByRole('button', { name: 'Zaktualizuj zapisaną trasę' }));
		expect(updateTrip).toHaveBeenCalledWith('trip-1', {
			name: 'Weekend in Kraków',
			date: '2026-07-11',
			optimizer_request: {
				place_ids: ['p1', 'p2'],
				transport_mode: 'WALK',
				day_start_hour: 9,
				day_end_hour: 21
			},
			optimizer_response: mockResult
		});
	});

	it('shows success toast after update', async () => {
		const { getByRole, getByText } = await renderAndOptimize();
		await userEvent.click(getByRole('button', { name: 'Zaktualizuj zapisaną trasę' }));
		await expect.element(getByText('Trasa "Weekend in Kraków" zaktualizowana!')).toBeVisible();
	});

	it('shows ApiError detail when update fails with 404', async () => {
		vi.mocked(updateTrip).mockRejectedValueOnce(new ApiError(404, "Trip 'trip-1' not found"));
		const { getByRole, getByText } = await renderAndOptimize();
		await userEvent.click(getByRole('button', { name: 'Zaktualizuj zapisaną trasę' }));
		await expect.element(getByText("Trip 'trip-1' not found")).toBeVisible();
	});

	it('shows generic failure message on unexpected error', async () => {
		vi.mocked(updateTrip).mockRejectedValueOnce(new Error('boom'));
		const { getByRole, getByText } = await renderAndOptimize();
		await userEvent.click(getByRole('button', { name: 'Zaktualizuj zapisaną trasę' }));
		await expect.element(getByText('Nie udało się zaktualizować trasy.')).toBeVisible();
	});
});
