import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import Page from './+page.svelte';
import { optimizeRoute } from '$lib/api/optimizer.js';
import { updateTrip } from '$lib/api/trips.js';
import { patchPlace } from '$lib/api/gmaps.js';
import { ApiError } from '$lib/api/client.js';
import * as m from '$lib/paraglide/messages.js';
import type { OptimizeResponse, PlaceOut, SkippedPlace, TripOut } from '$lib/types/index.js';
import type { OptimizerPrefill } from './+page.server.js';

vi.mock('$lib/api/optimizer.js', () => ({
	optimizeRoute: vi.fn()
}));

vi.mock('$lib/api/trips.js', () => ({
	updateTrip: vi.fn(),
	saveTrip: vi.fn()
}));

vi.mock('$lib/api/gmaps.js', () => ({
	patchPlace: vi.fn()
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
	priority: 'normal',
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

describe('/optimizer page — mark place as must-see', () => {
	const skipped: SkippedPlace[] = [
		{ place_id: 'p1', name: 'Wawel', reason: 'DROPPED_LOW_PRIORITY' }
	];
	const resultWithSkip: OptimizeResponse = { ...mockResult, skipped };
	const resultAfterUpdate: OptimizeResponse = {
		steps: [
			{
				place_id: 'p1',
				name: 'Wawel',
				lat: 50.0,
				lng: 20.0,
				arrival_time: '09:00:00',
				departure_time: '10:00:00',
				travel_from_previous_s: 0,
				visit_duration_min: 60,
				wait_min: 0
			}
		],
		total_travel_time_s: 0,
		total_visit_time_min: 60,
		total_wait_min: 0,
		transport_mode: 'WALK',
		skipped: []
	};

	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(optimizeRoute).mockResolvedValue(resultWithSkip);
		vi.mocked(patchPlace).mockResolvedValue({} as PlaceOut);
	});

	it('calls patchPlace with must_see priority when clicked', async () => {
		const { getByRole } = await renderAndOptimize();
		await userEvent.click(getByRole('button', { name: m.skipped_action_mark_must_see() }));
		expect(patchPlace).toHaveBeenCalledWith('p1', { priority: 'must_see' });
	});

	it('re-runs optimization with the original request after marking must-see', async () => {
		const { getByRole } = await renderAndOptimize();
		const originalRequest = vi.mocked(optimizeRoute).mock.calls[0][0];
		await userEvent.click(getByRole('button', { name: m.skipped_action_mark_must_see() }));
		await vi.waitFor(() => expect(optimizeRoute).toHaveBeenCalledTimes(2));
		expect(optimizeRoute).toHaveBeenLastCalledWith(originalRequest);
	});

	it('shows the rerun-success message after marking must-see', async () => {
		const { getByRole, getByText } = await renderAndOptimize();
		await userEvent.click(getByRole('button', { name: m.skipped_action_mark_must_see() }));
		await expect.element(getByText(m.optimizer_preference_updated_and_rerun())).toBeVisible();
	});

	it('shows the ApiError detail on failure', async () => {
		vi.mocked(patchPlace).mockRejectedValueOnce(new ApiError(404, "Place 'p1' not found"));
		const { getByRole, getByText } = await renderAndOptimize();
		await userEvent.click(getByRole('button', { name: m.skipped_action_mark_must_see() }));
		await expect.element(getByText("Place 'p1' not found")).toBeVisible();
		expect(optimizeRoute).toHaveBeenCalledTimes(1);
	});

	it('shows a generic failure message on unexpected error', async () => {
		vi.mocked(patchPlace).mockRejectedValueOnce(new Error('boom'));
		const { getByRole, getByText } = await renderAndOptimize();
		await userEvent.click(getByRole('button', { name: m.skipped_action_mark_must_see() }));
		await expect.element(getByText(m.optimizer_preference_update_failed())).toBeVisible();
		expect(optimizeRoute).toHaveBeenCalledTimes(1);
	});

	it('shows a rerun-failure message (not the generic preference-update failure) when the rerun fails', async () => {
		const updatedPlace: PlaceOut = { ...mockPlace('p1', 'Wawel'), priority: 'must_see' };
		vi.mocked(patchPlace).mockResolvedValueOnce(updatedPlace);
		vi.mocked(optimizeRoute)
			.mockResolvedValueOnce(resultWithSkip)
			.mockRejectedValueOnce(new ApiError(500, 'boom'));

		const { getByRole, getByText } = await renderAndOptimize();
		await userEvent.click(getByRole('button', { name: m.skipped_action_mark_must_see() }));

		await expect.element(getByText(m.optimizer_preference_updated_rerun_failed())).toBeVisible();
		expect(getByText(m.optimizer_preference_update_failed()).query()).toBeNull();
	});

	it('disables the button and prevents a duplicate call while promoting', async () => {
		let resolvePatch!: (place: PlaceOut) => void;
		vi.mocked(patchPlace).mockImplementationOnce(
			() =>
				new Promise((resolve) => {
					resolvePatch = resolve;
				})
		);

		const { getByRole } = await renderAndOptimize();
		await userEvent.click(getByRole('button', { name: m.skipped_action_mark_must_see() }));

		const button = getByRole('button', { name: m.optimizer_preference_updating() });
		await expect.element(button).toBeVisible();
		await expect.element(button).toBeDisabled();

		resolvePatch({ ...mockPlace('p1', 'Wawel'), priority: 'must_see' });
		await vi.waitFor(() => expect(patchPlace).toHaveBeenCalledTimes(1));
	});

	it('hides the mark-as-must-see button after a successful promotion', async () => {
		const updatedPlace: PlaceOut = { ...mockPlace('p1', 'Wawel'), priority: 'must_see' };
		vi.mocked(patchPlace).mockResolvedValueOnce(updatedPlace);
		vi.mocked(optimizeRoute)
			.mockResolvedValueOnce(resultWithSkip)
			.mockResolvedValueOnce(resultAfterUpdate);

		const { getByRole } = await renderAndOptimize();
		await userEvent.click(getByRole('button', { name: m.skipped_action_mark_must_see() }));

		await vi.waitFor(() =>
			expect(getByRole('button', { name: m.skipped_action_mark_must_see() }).query()).toBeNull()
		);
	});

	it('reflects the updated priority in the must-see-kept summary after re-optimizing', async () => {
		const updatedPlace: PlaceOut = { ...mockPlace('p1', 'Wawel'), priority: 'must_see' };
		vi.mocked(optimizeRoute)
			.mockResolvedValueOnce(resultWithSkip)
			.mockResolvedValueOnce(resultAfterUpdate);
		vi.mocked(patchPlace).mockResolvedValueOnce(updatedPlace);

		const { getByRole, getByTestId } = await renderAndOptimize();
		await userEvent.click(getByRole('button', { name: m.skipped_action_mark_must_see() }));

		const summary = getByTestId('route-summary');
		await vi.waitFor(() => {
			const text = (summary.element().textContent ?? '').replace(/\s+/g, ' ').trim();
			expect(text).toContain(`1/1 ${m.results_summary_must_see_kept()}`);
		});
	});
});
