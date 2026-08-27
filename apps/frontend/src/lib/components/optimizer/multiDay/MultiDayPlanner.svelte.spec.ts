import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import MultiDayPlanner from './MultiDayPlanner.svelte';
import { optimizeTrip } from '$lib/api/optimizer.js';
import { updateTrip } from '$lib/api/trips.js';
import type { MultiDayOptimizerPrefill } from './hydrateMultiDayState.js';
import type { MultiDayRequest, MultiDayResponse, PlaceOut, TripOut } from '$lib/types/index.js';

vi.mock('$lib/api/optimizer.js', () => ({
	optimizeTrip: vi.fn()
}));

vi.mock('$lib/api/trips.js', () => ({
	updateTrip: vi.fn(),
	saveTrip: vi.fn()
}));

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

const persistedRequest: MultiDayRequest = {
	days: [
		{ date: '2026-03-01', day_start_hour: 9, day_end_hour: 21 },
		{ date: '2026-03-02', day_start_hour: 9, day_end_hour: 21 }
	],
	places: [
		{ place_id: 'p1', day_preferences: [] },
		{ place_id: 'p2', day_preferences: [] }
	],
	transport_mode: 'WALK',
	accommodations: [],
	transfers: []
};

const persistedResponse: MultiDayResponse = {
	days: [
		{
			day_index: 0,
			date: '2026-03-01',
			steps: [],
			total_travel_time_s: 0,
			total_visit_time_min: 0,
			total_wait_min: 0,
			skipped: []
		},
		{
			day_index: 1,
			date: '2026-03-02',
			steps: [],
			total_travel_time_s: 0,
			total_visit_time_min: 0,
			total_wait_min: 0,
			skipped: []
		}
	],
	transport_mode: 'WALK',
	unassigned: []
};

const prefill: MultiDayOptimizerPrefill = {
	tripId: 'trip-1',
	tripName: 'Kraków then Warsaw',
	multiDayRequest: persistedRequest,
	multiDayResponse: persistedResponse
};

const updatedTrip: TripOut = {
	plan_type: 'MULTI_DAY',
	id: 'trip-1',
	name: 'Kraków then Warsaw',
	start_date: '2026-03-01',
	end_date: '2026-03-02',
	num_days: 2,
	created_at: '2026-03-01T10:00:00Z',
	updated_at: '2026-03-01T12:00:00Z',
	transport_mode: 'WALK',
	multi_day_request: persistedRequest,
	multi_day_response: persistedResponse
};

describe('MultiDayPlanner — fresh (no prefill)', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('shows no save/update buttons before any result exists', async () => {
		const { getByRole } = render(MultiDayPlanner, { props: { places, prefill: null } });
		expect(getByRole('button', { name: 'Zapisz trasę' }).query()).toBeNull();
		expect(getByRole('button', { name: 'Zaktualizuj zapisaną trasę' }).query()).toBeNull();
	});

	it('optimizing shows a plain save button (no update) since there is no source trip', async () => {
		vi.mocked(optimizeTrip).mockResolvedValue(persistedResponse);
		const { getByTestId, getByText, getByRole } = render(MultiDayPlanner, {
			props: { places, prefill: null }
		});
		await userEvent.click(getByText('Wawel'));
		await userEvent.click(getByText('Sukiennice'));
		await userEvent.click(getByTestId('multiday-submit'));
		await vi.waitFor(() => expect(optimizeTrip).toHaveBeenCalledOnce());
		await expect.element(getByRole('button', { name: 'Zapisz trasę' })).toBeVisible();
		expect(getByRole('button', { name: 'Zaktualizuj zapisaną trasę' }).query()).toBeNull();
	});
});

describe('MultiDayPlanner — reopened trip (prefill)', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(optimizeTrip).mockResolvedValue(persistedResponse);
		vi.mocked(updateTrip).mockResolvedValue(updatedTrip);
	});

	it('shows the persisted result immediately, without calling optimizeTrip', async () => {
		const { getByRole } = render(MultiDayPlanner, { props: { places, prefill } });
		await expect.element(getByRole('button', { name: 'Zapisz jako nową trasę' })).toBeVisible();
		expect(optimizeTrip).not.toHaveBeenCalled();
	});

	it('shows both update and save-as-new buttons for a reopened trip', async () => {
		const { getByRole } = render(MultiDayPlanner, { props: { places, prefill } });
		await expect.element(getByRole('button', { name: 'Zaktualizuj zapisaną trasę' })).toBeVisible();
		await expect.element(getByRole('button', { name: 'Zapisz jako nową trasę' })).toBeVisible();
	});

	it('editing the config marks the existing result stale without clearing it', async () => {
		const { getByText, getByTestId } = render(MultiDayPlanner, { props: { places, prefill } });
		// The itinerary (day tabs) is rendered from the persisted result.
		await expect.element(getByTestId('day-tab-0')).toBeVisible();

		await userEvent.click(getByText('Wawel'));

		await expect.element(getByTestId('stale-notice')).toBeVisible();
		// Result stays visible — the day tabs are still rendered.
		await expect.element(getByTestId('day-tab-0')).toBeVisible();
	});

	it('a DayRangeEditor edit (day count) marks the result stale', async () => {
		const { getByTestId, getByLabelText } = render(MultiDayPlanner, { props: { places, prefill } });
		await userEvent.fill(getByLabelText('Liczba dni'), '3');
		await expect.element(getByTestId('stale-notice')).toBeVisible();
	});

	it('an AccommodationEditor edit (adding a stay) marks the result stale', async () => {
		const { getByTestId } = render(MultiDayPlanner, { props: { places, prefill } });
		await userEvent.click(getByTestId('add-accommodation'));
		await expect.element(getByTestId('stale-notice')).toBeVisible();
	});

	it('a TransferEditor edit (enabling a transfer) marks the result stale', async () => {
		const transitionPrefill: MultiDayOptimizerPrefill = {
			...prefill,
			multiDayRequest: {
				...persistedRequest,
				accommodations: [
					{
						name: 'Hotel A',
						lat: 50,
						lng: 20,
						check_in_date: '2026-02-28',
						check_out_date: '2026-03-02'
					},
					{
						name: 'Hotel B',
						lat: 51,
						lng: 21,
						check_in_date: '2026-03-02',
						check_out_date: '2026-03-04'
					}
				]
			}
		};
		const { getByTestId } = render(MultiDayPlanner, {
			props: { places, prefill: transitionPrefill }
		});
		const row = getByTestId('transfer-row-2026-03-02');
		await userEvent.click(row.element().querySelector('input[type="checkbox"]')!);
		await expect.element(getByTestId('stale-notice')).toBeVisible();
	});

	it('disables save and update while the result is stale', async () => {
		const { getByText, getByRole } = render(MultiDayPlanner, { props: { places, prefill } });
		await userEvent.click(getByText('Wawel'));

		const updateBtn = getByRole('button', {
			name: 'Zaktualizuj zapisaną trasę'
		}).element() as HTMLButtonElement;
		const saveBtn = getByRole('button', {
			name: 'Zapisz jako nową trasę'
		}).element() as HTMLButtonElement;
		expect(updateBtn.disabled).toBe(true);
		expect(saveBtn.disabled).toBe(true);
	});

	it('a successful rerun clears staleness and re-enables save/update', async () => {
		const { getByTestId, getByRole, getByLabelText } = render(MultiDayPlanner, {
			props: { places, prefill }
		});
		// Edit transport mode — keeps the 2 required places intact, unlike toggling a place off.
		await getByLabelText('Transport').selectOptions('DRIVE');
		await expect.element(getByTestId('stale-notice')).toBeVisible();

		await userEvent.click(getByTestId('multiday-submit'));
		await vi.waitFor(() => expect(optimizeTrip).toHaveBeenCalledOnce());

		expect(getByTestId('stale-notice').query()).toBeNull();
		const updateBtn = getByRole('button', {
			name: 'Zaktualizuj zapisaną trasę'
		}).element() as HTMLButtonElement;
		expect(updateBtn.disabled).toBe(false);
	});

	it('update sends lastOptimizedRequest/result, never the edited-but-unrun editableState', async () => {
		const { getByRole } = render(MultiDayPlanner, { props: { places, prefill } });
		await userEvent.click(getByRole('button', { name: 'Zaktualizuj zapisaną trasę' }));
		expect(updateTrip).toHaveBeenCalledWith('trip-1', {
			name: 'Kraków then Warsaw',
			multi_day_request: persistedRequest,
			multi_day_response: persistedResponse
		});
	});

	it('shows a success toast after update', async () => {
		const { getByRole, getByText } = render(MultiDayPlanner, { props: { places, prefill } });
		await userEvent.click(getByRole('button', { name: 'Zaktualizuj zapisaną trasę' }));
		await expect.element(getByText('Trasa "Kraków then Warsaw" zaktualizowana!')).toBeVisible();
	});
});

describe('MultiDayPlanner — active day clamping', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('clamps activeDayIndex when a rerun returns fewer days than before', async () => {
		const threeDayResponse: MultiDayResponse = {
			days: [
				{
					day_index: 0,
					date: '2026-03-01',
					steps: [],
					total_travel_time_s: 0,
					total_visit_time_min: 0,
					total_wait_min: 0,
					skipped: []
				},
				{
					day_index: 1,
					date: '2026-03-02',
					steps: [],
					total_travel_time_s: 0,
					total_visit_time_min: 0,
					total_wait_min: 0,
					skipped: []
				},
				{
					day_index: 2,
					date: '2026-03-03',
					steps: [],
					total_travel_time_s: 0,
					total_visit_time_min: 0,
					total_wait_min: 0,
					skipped: []
				}
			],
			transport_mode: 'WALK',
			unassigned: []
		};
		const oneDayResponse: MultiDayResponse = {
			days: [
				{
					day_index: 0,
					date: '2026-03-01',
					steps: [],
					total_travel_time_s: 0,
					total_visit_time_min: 0,
					total_wait_min: 0,
					skipped: []
				}
			],
			transport_mode: 'WALK',
			unassigned: []
		};
		vi.mocked(optimizeTrip)
			.mockResolvedValueOnce(threeDayResponse)
			.mockResolvedValueOnce(oneDayResponse);

		const { getByText, getByTestId, getByLabelText } = render(MultiDayPlanner, {
			props: { places, prefill: null }
		});
		await userEvent.click(getByText('Wawel'));
		await userEvent.click(getByText('Sukiennice'));
		await userEvent.click(getByTestId('multiday-submit'));
		await vi.waitFor(() => expect(optimizeTrip).toHaveBeenCalledTimes(1));

		// Move to the last (3rd) day tab before shrinking the range.
		await userEvent.click(getByTestId('day-tab-2'));

		await userEvent.fill(getByLabelText('Liczba dni'), '1');
		await userEvent.click(getByTestId('multiday-submit'));
		await vi.waitFor(() => expect(optimizeTrip).toHaveBeenCalledTimes(2));

		// Only one day tab exists now, and rendering did not crash on an out-of-range index.
		expect(getByTestId('day-tab-0')).toBeTruthy();
		expect(getByTestId('day-tab-1').query()).toBeNull();
	});
});
